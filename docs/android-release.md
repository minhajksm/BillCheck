# Releasing the Android app to Google Play

Play takes an Android App Bundle (`.aab`), signed with FairCare's **upload
key**. Google re-signs it with the app signing key it keeps for you (Play App
Signing), so the upload key only proves an upload came from you.

`app/plugins/with-release-signing.js` makes release builds use the upload
key. The key itself is in `app/credentials/`, which is gitignored and must
never be committed.

## Once: make the upload key

Run from the `app` folder. On Windows, `keytool` comes with Android Studio.
If PowerShell doesn't recognise it, use the full path, usually
`& "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"`.

```powershell
mkdir credentials
keytool -genkeypair -v -storetype PKCS12 -keystore credentials\upload.keystore -alias upload -keyalg RSA -keysize 2048 -validity 10000
```

It asks for a password (twice) and a name. Then create
`app\credentials\upload-keystore.properties` with this content, using the
password you just chose for both entries:

```properties
storeFile=upload.keystore
storePassword=THE_PASSWORD
keyAlias=upload
keyPassword=THE_PASSWORD
```

**Back up both files and the password** somewhere other than this computer,
such as a password manager. If the upload key is lost, Play support can
reset it, but that takes days and blocks releases meanwhile.

## Every release

1. **Raise `versionCode`** in `app/app.json` (`expo.android.versionCode`).
   Play refuses a bundle whose number it has seen before. `1`, then `2`, and
   so on. Change `expo.version` (shown to users, e.g. `1.0.1`) when you
   like.
2. **Build.** In PowerShell, from the `app` folder. `EXPO_PUBLIC_API_URL` is
   baked into the app at build time. Without it, the app tries to reach
   `10.0.2.2`, which only exists inside the emulator.

   ```powershell
   $env:EXPO_PUBLIC_API_URL = "https://YOUR-API-ADDRESS"
   npx expo prebuild --platform android --clean
   cd android
   .\gradlew.bat bundleRelease
   cd ..
   ```

   The bundle is at `app\android\app\build\outputs\bundle\release\app-release.aab`.
3. **Upload** it in Play Console, in the testing track or production
   release you're preparing.

If Play says the bundle is signed in debug mode, the properties file wasn't
found. Check it is at `app\credentials\upload-keystore.properties`, exactly
that name, and build again.
