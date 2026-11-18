# patches

OpenJarvis-la change venum-na, patch file-ah inga vai.

## Patch create panna

```powershell
cd OpenJarvis
# edit pannu
git diff > ..\patches\maya-01-my-change.patch
git checkout -- .      # original-ku thirumba
```

## Patch apply panna

Update script auto-ah apply pannum.
Manual:

```powershell
git -C OpenJarvis apply ..\patches\maya-01-my-change.patch
```

Status: Empty — patch onnum illa.
