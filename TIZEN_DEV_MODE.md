# Installing Apps on Samsung Tizen TVs (Developer Mode)

Tizen does have an official developer mode, unlike webOS's community homebrew route. It's more limited though.

## Enabling Developer Mode on the Samsung TV

1. Go to **Apps**
2. On the remote, type `12345` (using the number pad, or on-screen keyboard if no numpad) — this brings up a Developer Mode dialog
3. Toggle Developer Mode **ON**, enter your PC's IP address (the machine you'll install apps from)
4. Restart the TV

## Installing apps

Once dev mode is on, you install via **Tizen Studio** (Samsung's official IDE, free download) on a PC:

- Tizen Studio connects to the TV over your local network using the IP you entered
- You can install `.wgt` packages (Tizen's app format, essentially a signed web app bundle) this way
- There is no equivalent to sideloading an arbitrary APK — Tizen apps are HTML5/JS/CSS-based (or native C++ with Tizen SDK), not Android

## The catch for something like SmartTube

There's no SmartTube build for Tizen. The Tizen homebrew scene is much smaller than webOS's — a few community devs have built ad-blocking YouTube clients as `.wgt` apps in the past, but they're inconsistent, often break with Samsung firmware updates, and aren't actively maintained the way SmartTube is for Android TV. Search around for something like "YouTube ad-free Tizen wgt" and you may find a working one, but there's no guarantee of long-term support.

Given that, an Android TV box is still the more reliable path if ad-free YouTube matters to you.
