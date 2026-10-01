import zipfile,os
apk=r"C:/Users/19136/Desktop/梦幻神域_UC_2662808_105628864d2d.apk"
z=zipfile.ZipFile(apk)
os.makedirs(r"work\extract",exist_ok=True)
for n in ['assets/bin/Data/Managed/Assembly-CSharp.dll','assets/bin/Data/Managed/ClientCore.dll','assets/bin/Data/Managed/UIRunTimeScript.dll','assets/bin/Data/Managed/Assembly-UnityScript.dll']:
    d=z.read(n); out=os.path.join(r"work\extract",n.split('/')[-1])
    open(out,'wb').write(d); print(out,len(d))
