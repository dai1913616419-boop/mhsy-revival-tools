#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 APK 做 v1（jarsigner）签名 —— 在本机没有 JDK 时使用。

背景：Android 装 APK 必须签名。改了 APK 内容后原签名失效，
而本机没有 java/keytool/jarsigner，所以用 cryptography 手工实现 v1 签名：
  META-INF/MANIFEST.MF  每个条目的摘要
  META-INF/CERT.SF      对 MANIFEST 的摘要
  META-INF/CERT.RSA     PKCS#7 detached 签名

用法：
  python sign_apk.py <输入.apk> [--out 输出.apk] [--inplace]

通常与 patch_apk_version.py 搭配：
  python patch_apk_version.py --host 192.168.0.12   # 产出未签名副本（会提示签名失败）
  python sign_apk.py <原apk路径>.patched.apk --inplace
"""

import argparse
import base64
import datetime
import hashlib
import os
import sys
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

DIGEST_ATTR = "SHA-256-Digest"
HASH = hashlib.sha256
HASH_ALG = hashes.SHA256()
SIGN_ALG = padding.PKCS1v15()   # 配合 SHA256 -> SHA256withRSA


def fold(value: str) -> bytes:
    """按 JAR manifest 规范折行：每行不超过 72 字节，续行以空格开头。"""
    raw = value.encode("utf-8")
    chunks = []
    first = True
    i = 0
    while i < len(raw):
        limit = 72 if first else 71
        chunk = raw[i:i + limit]
        chunks.append(chunk if first else b" " + chunk)
        i += limit
        first = False
    return b"\r\n".join(chunks) + b"\r\n"


def make_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MHLocal"),
        x509.NameAttribute(NameOID.COMMON_NAME, "mhsy-local"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .sign(key, HASH_ALG))
    return key, cert


def build_manifest(entries):
    """entries: [(name, sha256_hex)] -> MANIFEST.MF 字节 + 每个 entry 的块字节"""
    out = b"Manifest-Version: 1.0\r\nCreated-By: MHLocalSigner\r\n\r\n"
    blocks = {}
    for name, digest_hex in entries:
        b64 = base64.b64encode(bytes.fromhex(digest_hex)).decode()
        block = fold("Name: %s" % name) + fold("%s: %s" % (DIGEST_ATTR, b64)) + b"\r\n"
        blocks[name] = block
        out += block
    return out, blocks


def build_sf(manifest_bytes, blocks):
    manifest_digest = base64.b64encode(HASH(manifest_bytes).digest()).decode()
    out = (b"Signature-Version: 1.0\r\n"
           b"Created-By: MHLocalSigner\r\n"
           + fold("%s-Manifest: %s" % (DIGEST_ATTR, manifest_digest))
           + b"\r\n")
    for name, block in blocks.items():
        b64 = base64.b64encode(HASH(block).digest()).decode()
        out += fold("Name: %s" % name) + fold("%s: %s" % (DIGEST_ATTR, b64)) + b"\r\n"
    return out


# ---------------------------------------------------------------- DER 工具
# 说明：cryptography 的 pkcs7 生成器会写入 SMIMECapability 认证属性，
# Android 的 JarVerifier 解析时抛 "rejects tag type -96" 而拒绝安装。
# 因此这里手写最小 PKCS#7 SignedData，只保留 contentType + messageDigest。

OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
OID_DATA = "1.2.840.113549.1.7.1"
OID_SHA256 = "2.16.840.1.101.3.4.2.1"
OID_RSA = "1.2.840.113549.1.1.1"
OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(value)) + value


def der_oid(dotted: str) -> bytes:
    parts = [int(x) for x in dotted.split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunks = [p & 0x7F]
        p >>= 7
        while p:
            chunks.append((p & 0x7F) | 0x80)
            p >>= 7
        out += bytes(reversed(chunks))
    return out


def der_int(n: int) -> bytes:
    b = n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big")
    return tlv(0x02, b)


def alg(dotted: str, with_null=True) -> bytes:
    """AlgorithmIdentifier"""
    body = tlv(0x06, der_oid(dotted))
    if with_null:
        body += tlv(0x05, b"")
    return tlv(0x30, body)


def attr(dotted: str, values: list) -> bytes:
    """Attribute ::= SEQUENCE { OID, SET OF value }"""
    return tlv(0x30, tlv(0x06, der_oid(dotted)) + tlv(0x31, b"".join(values)))


def build_rsa(sf_bytes, key, cert):
    """构造 detached PKCS#7 SignedData（CERT.RSA 的内容）。"""
    digest = hashlib.sha256(sf_bytes).digest()

    # 认证属性：签名时按 SET OF (0x31) 编码
    attrs = [
        attr(OID_ATTR_CONTENT_TYPE, [tlv(0x06, der_oid(OID_DATA))]),
        attr(OID_ATTR_MESSAGE_DIGEST, [tlv(0x04, digest)]),
    ]
    signed_attrs_body = b"".join(attrs)
    signed_attrs_der = tlv(0x31, signed_attrs_body)       # 用于计算签名
    signature = key.sign(signed_attrs_der, padding.PKCS1v15(), HASH_ALG)

    # SignerInfo
    issuer_der = cert.issuer.public_bytes()
    signer_info = tlv(0x30,
                      der_int(1)
                      + tlv(0x30, issuer_der + der_int(cert.serial_number))
                      + alg(OID_SHA256)
                      + tlv(0xA0, signed_attrs_body)      # [0] IMPLICIT SET OF
                      + alg(OID_RSA)
                      + tlv(0x04, signature))

    cert_der = cert.public_bytes(serialization.Encoding.DER)

    signed_data = tlv(0x30,
                      der_int(1)
                      + tlv(0x31, alg(OID_SHA256))
                      + tlv(0x30, tlv(0x06, der_oid(OID_DATA)))   # 无内容(detached)
                      + tlv(0xA0, cert_der)                        # [0] IMPLICIT certificates
                      + tlv(0x31, signer_info))

    return tlv(0x30, tlv(0x06, der_oid(OID_SIGNED_DATA)) + tlv(0xA0, signed_data))


def sign(src, dst):
    print("读取: %s" % src)
    with zipfile.ZipFile(src, "r") as z:
        infos = [i for i in z.infolist() if not i.filename.startswith("META-INF/")]
        entries = []
        for info in infos:
            h = hashlib.sha256()
            with z.open(info.filename) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            entries.append((info.filename, h.hexdigest()))
        print("  待签名条目: %d" % len(entries))

        manifest, blocks = build_manifest(entries)
        sf = build_sf(manifest, blocks)
        key, cert = make_keypair()
        rsa_der = build_rsa(sf, key, cert)
        print("  MANIFEST.MF %d 字节, CERT.SF %d 字节, CERT.RSA %d 字节"
              % (len(manifest), len(sf), len(rsa_der)))

        print("写出: %s" % dst)
        with zipfile.ZipFile(dst, "w") as out:
            for info in z.infolist():
                if info.filename.startswith("META-INF/"):
                    continue  # 丢弃旧签名
                data = z.read(info.filename)
                ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                ni.compress_type = info.compress_type
                ni.external_attr = info.external_attr
                out.writestr(ni, data)
            for name, data in (("META-INF/MANIFEST.MF", manifest),
                               ("META-INF/CERT.SF", sf),
                               ("META-INF/CERT.RSA", rsa_der)):
                ni = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                ni.compress_type = zipfile.ZIP_DEFLATED
                ni.external_attr = 0o644 << 16
                out.writestr(ni, data)

    # 回读校验
    with zipfile.ZipFile(dst, "r") as z:
        names = z.namelist()
        ok = all(n in names for n in ("META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA"))
        print("  校验: %s" % ("✓ META-INF 三件套齐全" % () if ok else "✗ 缺少签名文件"))
        return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="纯 Python 实现 APK v1 签名")
    ap.add_argument("apk")
    ap.add_argument("--out", default=None)
    ap.add_argument("--inplace", action="store_true")
    args = ap.parse_args()

    src = args.apk
    if not os.path.isfile(src):
        print("找不到: %s" % src)
        return 1
    dst = src if args.inplace else (args.out or (os.path.splitext(src)[0] + ".signed.apk"))
    if args.inplace:
        tmp = src + ".tmp"
        rc = sign(src, tmp)
        if rc == 0:
            os.replace(tmp, src)
            print("已就地签名: %s" % src)
        elif os.path.exists(tmp):
            os.remove(tmp)
        return rc
    return sign(src, dst)


if __name__ == "__main__":
    sys.exit(main())
