# Keyboard & Mouse Switch

A small Windows-to-Windows prototype that lets one machine's keyboard and mouse control a second computer over your local network. The receiver needs its own screen. Both machines run Python scripts; no installer or packaging is required.

## Setup (both computers)

Open PowerShell in the project folder and run:

```powershell
uv sync
```

This creates a project-local `.venv` and installs the locked dependencies. You do not need to activate it; `uv run` uses it automatically. Install uv on each computer if needed: see [uv installation](https://docs.astral.sh/uv/getting-started/installation/).

## Run (both computers)

```powershell
uv run python main.py
```

Or double-click `start.bat`.

A window opens where you select whether the machine should act as **Controller** or **Receiver**. You can switch roles at any time using **Switch Role**.

### On the Receiver

Select **Start as Receiver** and keep the window open. It displays local IPv4 addresses, port, certificate fingerprint, and pairing secret (with **Copy** buttons). If several IPs are shown, choose the one belonging to the active network adapter; run `ipconfig` if unsure. The first run generates `receiver-data` locally. Keep its contents private; it is excluded from Git.

If Windows Firewall asks, allow Python access to **private networks**. If the connection times out, check the machines are on the same local network and that the firewall permits inbound TCP port 45839 on the receiver. Guest Wi-Fi or client isolation can prevent the devices from communicating.

### On the Controller

Select **Start as Controller**. The first time, enter the receiver IP address, port, certificate fingerprint, and pairing secret shown on the receiver. Check the fingerprint directly against the receiver's display: it pins the receiver's certificate and protects the secret and input stream from an impersonator. After a successful connection, the controller remembers the details and tries to reconnect to the most recently connected receiver automatically next time it starts. You can select another previously connected receiver from **Saved receivers**, then click **Connect**. The saved pairing is encrypted using Windows data protection for your Windows user account, in `%LOCALAPPDATA%\KeyboardMouseSwitch\pairing.bin`. The receiver keeps the same fingerprint and secret until its `receiver-data` is reset. If the receiver IP address changes, enter its new address and connect; the new address is remembered. If the receiver was not running when the controller started, start it and press **Connect** to retry.

Choose a **Scroll speed** on the controller (the default is 50%). Press **Connect**, then **Receiver**. Keyboard and mouse input now go to the receiver. Press **Ctrl + Alt + Space** to return control to the controller. Use the **Controller** button when controller control is active; the shortcut is needed while the receiver has the mouse. Close either app or disconnect to return control to the controller.

The shortcut releases forwarded keys and mouse buttons on the receiver. If a connection fails, the receiver also releases inputs once it detects the disconnect. If control does not return immediately after an unexpected network failure, use Ctrl + Alt + Space; an ordinary TCP connection may take time to detect a cable or Wi-Fi failure.

## Security and limitations

- The connection uses TLS with a pinned, self-signed certificate and a randomly generated pairing secret. The secret grants control of the receiver: share it only with trusted users. The listener binds to all local interfaces and accepts one connection at a time. Keep the receiver on a trusted private network.
- To forget the controller pairing, close the controller and delete `%LOCALAPPDATA%\KeyboardMouseSwitch\pairing.bin`. The `receiver-data` folder contains the private key and secret. Delete it while the receiver is stopped to generate a new identity and secret. Copy the new fingerprint and secret to the controller.
- This is a prototype. Windows secure screens, Ctrl+Alt+Delete, elevated application windows, some games and software that uses raw input may not accept forwarded input. Different keyboard layouts can affect characters. High-resolution scrolling is accumulated into whole wheel steps, so low scroll speeds can feel less smooth.
- The first version relies on Windows input hooks and simulated input, and does not stream a screen, share a clipboard, or automatically start with Windows. It needs a live interactive Windows session on each machine.
- Test the switch and shortcut with a second local mouse or keyboard available on the receiver. The shortcut only works when the controller is running and Windows is accepting keyboard input.
