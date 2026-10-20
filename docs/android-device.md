# Running the app on an Android phone

What it takes to make this work on Windows, with a phone on a USB cable:

```powershell
cd app
$env:EXPO_PUBLIC_API_URL = "https://your-api.example"
npx expo run:android --device
```

Once it is set up, the first build takes 10–20 minutes and every one after it
is fast — and a change to JavaScript, which is most changes, reloads on the
phone without rebuilding at all. That is the reason to do this rather than
wait on cloud builds.

The alternative, if you would rather install nothing, is EAS Build: see
[the app section of deploy.md](deploy.md#3-the-app).

## 1. Android Studio

Install [Android Studio](https://developer.android.com/studio). Accept the
default install location; the steps below assume it.

You will not write any code in it. It is here for three things the build
needs: the SDK, the build tools, and `adb`.

## 2. Install the SDK pieces this project needs

At Expo 57 and React Native 0.86 this project compiles against **API 36**
(Android 16) — the default `expo-modules-core` supplies.

Open **SDK Manager**: from the welcome screen it is under **More Actions**;
with a project open it is **Tools → SDK Manager**. Both are the same panel as
*Settings → Languages & Frameworks → Android SDK*.

- *SDK Platforms* tab → tick **Android 16.0 ("Baklava", API 36)**.
- *SDK Tools* tab → tick **Android SDK Build-Tools**, **Android SDK
  Platform-Tools** and **Android SDK Command-line Tools**.
- Still in *SDK Tools*, tick **Show Package Details** and add **NDK (Side by
  side)** and **CMake**. Several dependencies here — `react-native-screens`
  and `react-native-worklets` among them — compile C++, and without these the
  build gets a long way in and then fails on
  `Task :react-native-screens:configureCMakeDebug[arm64-v8a] FAILED`.
- Apply, and let it download. The NDK alone is a couple of gigabytes.

Which NDK and CMake version: the ones this project asks for.

```powershell
Select-String -Path app\android\build.gradle -Pattern "ndkVersion"
```

If a build has already failed, its `FAILURE:` block names them outright —
"No version of NDK matched the requested version ..." or "CMake '3.22.1' was
not found in SDK, PATH, or by cmake.dir property".

All of this works from the command line too, which is quicker than hunting
through checkboxes and shows you every version on offer:

```powershell
$sdkmanager = "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat"
& $sdkmanager --list | Select-String "ndk;|cmake;|platforms;android-36"
& $sdkmanager "platforms;android-36" "ndk;27.1.12297006" "cmake;3.22.1"
```

That number is tied to the Expo and React Native versions in
`package.json`, so it moves on an upgrade. Nothing in `android/build.gradle`
spells it out — the template leaves it to the Expo plugin's default — so to
check it after an upgrade, search the generated folder rather than one file:

```powershell
Get-ChildItem app\android -Recurse -Include *.gradle,*.properties -File |
  Select-String -Pattern "(?i)compilesdk|targetsdk|minsdk|buildtools"
```

If that also comes back empty, the defaults are in force and the answer is
whatever `node_modules\expo-modules-core\android\ExpoModulesCorePlugin.gradle`
has on its `safeExtGet("compileSdkVersion", ...)` line.

Getting it wrong is not expensive, either way: Gradle fails naming the exact
platform it wanted, and Android Studio offers to install it.

## 3. Two environment variables

Gradle needs a JDK, and the Expo CLI needs to know where the SDK is. Android
Studio bundles a suitable JDK, so there is nothing more to install:

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
$jdk = "C:\Program Files\Android\Android Studio\jbr"

[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk, "User")

# Read the User-scope Path, not $env:Path -- appending that would copy every
# machine-wide entry into your own profile.
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$sdk\platform-tools", "User")
```

**Close every PowerShell window and open a new one** — these are read at
startup. Then check both:

```powershell
adb version                                   # 1.0.41 or similar
Test-Path "$env:JAVA_HOME\bin\java.exe"       # True
& "$env:JAVA_HOME\bin\java.exe" -version      # 17.x
```

Note that `java -version` on its own will *not* work, and does not need to:
only `JAVA_HOME` is set above, not the JDK's `bin` directory on `Path`, and
Gradle reads `JAVA_HOME`. Adding it to `Path` as well is a matter of taste.

If `adb` is not recognised, `$sdk\platform-tools\adb.exe` does not exist,
which means step 2's Platform-Tools did not install. If `Test-Path` says
`False`, Android Studio went somewhere else; find its JDK with

```powershell
Get-ChildItem "C:\Program Files\Android" -Recurse -Depth 3 -Filter java.exe -ErrorAction SilentlyContinue |
  Select-Object -First 5 FullName
```

and set `JAVA_HOME` to the directory that contains that `bin`.

## 4. The phone

1. *Settings → About phone →* tap **Build number** seven times. It says
   "You are now a developer".
2. *Settings → System → Developer options* → turn on **USB debugging**.
3. Connect the phone by USB. **Use a cable that carries data** — a
   charge-only cable shows nothing and gives no error.
4. The phone shows *Allow USB debugging?* with a fingerprint. Tick *Always
   allow* and accept. If no prompt appears, unlock the phone and unplug and
   replug it.
5. Some phones also need *Install via USB* enabled in Developer options,
   usually the Xiaomi, Oppo and Vivo families.

Check the computer can see it:

```powershell
adb devices
```

You want `<serial>  device`. `unauthorized` means step 4 was not accepted;
an empty list means the cable, the port or USB debugging.

## 5. Build and run

```powershell
cd app
$env:EXPO_PUBLIC_API_URL = "https://your-api.example"
npx expo run:android --device
```

**`EXPO_PUBLIC_API_URL` is not optional here.** It is read when the bundle is
built, not when the app runs, and without it the app falls back to
`http://10.0.2.2:8000` — the emulator's alias for your computer, which means
nothing on a real phone. The app would start and then fail to reach anything.

The first run downloads Gradle and the dependency graph: 10–20 minutes, and a
few gigabytes. After that, `npx expo start` alone is enough — the installed
app connects back to Metro and JavaScript changes reload on the phone.

## When it goes wrong

| What you see | What it is |
| --- | --- |
| `Failed to resolve the Android SDK path` | `ANDROID_HOME` not set, or set in a window opened before step 3. Open a new terminal. |
| `'adb' is not recognized` | `platform-tools` not on `Path`, same cause. |
| `Unsupported class file major version` or a Gradle JDK complaint | `JAVA_HOME` points at the wrong Java. Point it at Android Studio's `jbr`. `java -version` failing is not this, and not a problem: `java` is not on `Path` and Gradle does not use it. |
| `An Application Control policy has blocked this file` | Windows Smart App Control, the same thing that blocked `uv` earlier. It has to be turned off in *Windows Security → App & browser control*, and that needs a reinstall of Windows to turn back on — so weigh it. |
| `INSTALL_FAILED_USER_RESTRICTED` | The phone refused the install: enable *Install via USB* in Developer options. |
| App installs, then "couldn't connect" | `EXPO_PUBLIC_API_URL` was not set when it was built. Rebuild with it. |
| `Could not determine java version` / Gradle stalls at 0% | A proxy or antivirus intercepting Gradle's downloads. |
| `:<module>:configureCMakeDebug[arm64-v8a] FAILED` | The NDK or CMake is missing. Step 2. The failure names the version it wanted. |

`npx expo run:android --device` with more than one device attached asks which
one. `adb devices` first saves the guesswork.
