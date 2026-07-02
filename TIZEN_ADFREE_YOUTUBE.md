# Ad-Free YouTube on a Samsung Tizen TV (TizenTube)

Good news: a SmartTube-equivalent for Tizen already exists and is actively maintained — **TizenTube**, installed through **TizenBrew** (a homebrew module manager for Tizen TVs, both by the same developer, reisxd). As of early 2026 it still works: no ads during playback, plus SponsorBlock, DeArrow, playback speed controls, and theming on top of the normal YouTube TV interface.

This is the reliable path. Writing a YouTube client from scratch isn't practical — YouTube changes its internals constantly and unmaintained one-off clients break within months, which is exactly why SmartTube/TizenTube survive: they have active maintainers.

## What you need

- A Samsung TV from **2017 or newer** (Tizen 3.0+). Newest models/firmware occasionally lag support — check the TizenBrew project page if the install fails.
- A PC, Mac, or Linux machine **on the same network** as the TV.
- The **TizenBrew Installer** desktop app — no full Tizen Studio required.

## Step 1 — Enable Developer Mode on the TV

1. Open **Apps** on the TV.
2. Type `12345` on the remote's number pad (or the on-screen keypad). A Developer Mode dialog appears.
3. Toggle Developer Mode **ON** and enter your **PC's IP address**.
4. Restart the TV.

## Step 2 — Find the TV's IP address

**Settings → General → Network → Network Status** (path varies slightly by model year). Note the IP.

## Step 3 — Install TizenBrew from your PC

1. Download the **TizenBrew Installer** for your OS from the TizenBrew GitHub releases page: <https://github.com/reisxd/TizenBrew>
2. Run it, enter the TV's IP address, and let it connect and install. It handles the certificate/signing dance that would otherwise require Tizen Studio.
3. **On Tizen 7 or newer** (2023+ TVs, including the 2024 DU-series): the installer will prompt you to **sign in with a Samsung account** to create a Samsung certificate — follow the on-screen instructions. Use the same Samsung account that's signed in on the TV.

## Step 4 — Launch TizenTube

1. Open the **TizenBrew** app that now appears on the TV.
2. TizenTube is available in the module launcher — select and launch it. (If it isn't listed, add the module `@foxreis/tizentube`.)
3. You get the familiar YouTube TV interface, minus the ads. Sign in with your Google account if you want your subscriptions/history. SponsorBlock and other extras are configurable in TizenTube's settings.

## Caveats

- **Firmware updates can remove it.** Samsung firmware updates sometimes wipe dev-mode apps or break TizenBrew; reinstalling via the same steps usually fixes it. Consider disabling auto-update on the TV if this bothers you.
- **Keep Developer Mode on.** Turning it off can disable the installed apps.
- **It's a cat-and-mouse game.** YouTube changes things; TizenTube gets updated. TizenBrew can update modules from the TV, so check for module updates if ads reappear.
- **Fallback:** if your model isn't supported, an Android TV / Google TV / Fire TV box running SmartTube remains the most robust option.

## Sources

- [TizenTube official site](https://tizentube.app/)
- [TizenTube on GitHub (reisxd/TizenTube)](https://github.com/reisxd/TizenTube)
- [TizenBrew + TizenTube install guide for 2023–2025 TVs, Tizen 6–8](https://gist.github.com/TurkeyJives/145672fe4b99e7ec89205f7807fe246c)
- [Bob Matyas: Using TizenTube for ad-free YouTube on Samsung TVs](https://bobmatyas.com/blog/using-tizentube-for-ad-free-youtube-viewing-on-samsung-tvs/)
- [TROYPOINT TizenTube guide](https://troypoint.com/tizentube/)
