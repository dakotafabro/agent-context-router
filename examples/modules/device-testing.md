## Device Testing

- Run `adb devices` first. When more than one device is attached, set `ANDROID_SERIAL` or pass `adb -s <serial>` on every command.
- Before sending input, check the foreground app with `adb shell dumpsys activity activities | grep topResumedActivity`.
- Clean up only what this session installed.
