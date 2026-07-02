# Ad-Free YouTube on Your Samsung TV — Simple Step-by-Step Guide

This installs **TizenTube** on your Samsung TV. It's YouTube with no ads. It works on your TV (UN50DU6900, 2024 model). It's free.

**What you need before starting:**

- Your Samsung TV
- A Windows PC or Mac
- Both must be connected to the **same Wi-Fi network**
- About 20 minutes

---

## Part 1: Find your PC's IP address

You'll need to type this number into the TV in Part 2, so write it down.

**On Windows:**

1. Press the **Windows key** on your keyboard.
2. Type `cmd` and press **Enter**. A black window opens.
3. Type `ipconfig` and press **Enter**.
4. Look for the line that says **IPv4 Address**. It looks like `192.168.1.23`.
5. Write that number down. This is your **PC's IP address**.

**On Mac:**

1. Click the **Apple menu** (top-left corner) → **System Settings**.
2. Click **Wi-Fi** on the left.
3. Click the **Details...** button next to your Wi-Fi network name.
4. You'll see **IP Address**, like `192.168.1.23`.
5. Write that number down. This is your **PC's IP address**.

## Part 2: Turn on Developer Mode on the TV

1. On the TV, press the **Home** button on the remote.
2. Go to **Apps**.
3. While on the Apps screen, type **1 2 3 4 5** on the remote. (If your remote has no number buttons, press and hold the **123** button, or select the number pad on screen.)
4. A hidden **Developer Mode** window pops up.
5. Turn Developer Mode **On**.
6. Where it asks for **Host PC IP**, type the **PC's IP address** you wrote down in Part 1.
7. Click **OK**.
8. Turn the TV **off**, wait 5 seconds, and turn it back **on**. (This restart is required.)

## Part 3: Find the TV's IP address

You'll need to type this number into your PC in Part 4, so write it down.

1. On the TV, press **Home** on the remote.
2. Go to **Settings** (the gear icon).
3. Go to **All Settings** → **General & Privacy** → **Network** → **Network Status**.
4. Select **IP Settings**.
5. You'll see **IP Address**, like `192.168.1.45`.
6. Write that number down. This is your **TV's IP address**.

## Part 4: Install TizenBrew from your PC

1. On your PC, open a web browser and go to: **https://github.com/reisxd/TizenBrew/releases/latest**
2. Under **Assets**, download the installer for your computer:
   - Windows: the file ending in **.exe**
   - Mac: the file ending in **.dmg**
3. Open the downloaded file to run the **TizenBrew Installer**. (Windows may warn you about an unknown app — click **More info** → **Run anyway**.)
4. Make sure the TV is **turned on**.
5. In the installer, type your **TV's IP address** (from Part 3) and click **Connect**.
6. Follow the instructions on the screen. Because your TV is a 2024 model, it will ask you to **sign in with your Samsung account** — use the same Samsung account that's signed in on the TV. This is normal; it creates a certificate needed to install apps.
7. Wait for the installer to say it's **done**. TizenBrew is now installed on the TV.

## Part 5: Watch YouTube without ads

1. On the TV, press **Home** and go to **Apps**.
2. Open the new app called **TizenBrew**.
3. Select **TizenTube** and launch it.
4. That's it — this is YouTube with no ads. Sign in with your Google account inside TizenTube if you want your subscriptions and history.

From now on, just open **TizenBrew → TizenTube** whenever you want to watch YouTube.

---

## If something goes wrong

- **The Developer Mode window doesn't pop up when typing 12345:** Make sure you're on the **Apps** screen (not the home screen) when you type it.
- **The installer can't connect to the TV:** Check that the TV and PC are on the **same Wi-Fi**, the TV is on, and Developer Mode shows **On** with your PC's IP.
- **TizenTube disappeared after a TV update:** Samsung updates sometimes remove it. Just repeat Parts 4–5 to reinstall. To prevent this: **Settings → Support → Software Update → turn Auto Update off**.
- **Ads came back:** Open TizenBrew and check for a TizenTube update.
- **Don't turn Developer Mode off** — the app stops working without it.

## Sources

- [TizenBrew on GitHub](https://github.com/reisxd/TizenBrew)
- [TizenTube official site](https://tizentube.app/)
- [TizenBrew + TizenTube install guide for 2023–2025 TVs, Tizen 6–8](https://gist.github.com/TurkeyJives/145672fe4b99e7ec89205f7807fe246c)
- [Bob Matyas: Using TizenTube for ad-free YouTube on Samsung TVs](https://bobmatyas.com/blog/using-tizentube-for-ad-free-youtube-viewing-on-samsung-tvs/)
- [TROYPOINT TizenTube guide](https://troypoint.com/tizentube/)
