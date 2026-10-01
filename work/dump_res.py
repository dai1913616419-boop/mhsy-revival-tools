import zipfile,sys
apk=r"C:/Users/19136/Desktop/梦幻神域_UC_2662808_105628864d2d.apk"
name="assets/bin/Data/7bcccccbb6d31a741b30b3f77d8d946c"
z=zipfile.ZipFile(apk)
d=z.read(name)
print("size",len(d))
open(r"work\res_7bcc.bin","wb").write(d)
# find offsets of interest
for kw in [b"360joy",b"Version",b"IncrementPack",b"http"]:
    i=0
    while True:
        i=d.find(kw,i)
        if i<0: break
        print(kw, i, d[max(0,i-120):i+160])
        i+=1
    print("-"*40)
