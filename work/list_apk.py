import zipfile,re
apk=r"C:/Users/19136/Desktop/梦幻神域_UC_2662808_105628864d2d.apk"
z=zipfile.ZipFile(apk)
for n in z.namelist():
    if re.search(r'\.(dll|so|bytes|txt|json|xml)$',n,re.I):
        print(z.getinfo(n).file_size,"\t",n)
