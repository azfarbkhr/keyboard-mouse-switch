# Keyboard & Mouse Switch

A small Windows-to-Windows prototype that lets one laptop keyboard and mouse control a second computer over your local network. The PC needs its own screen. Both machines run Python scripts; no installer or packaging is required.

## Requirements

- Windows 10 or 11 on both computers, with uv and Python 3.10 or newer (including Tkinter).
- Both computers must be able to reach one another on the local network. Wi-Fi on the laptop and Ethernet on the PC is fine.
- Copy this project folder to both computers. Do not copy `receiver-data`: the PC creates its own keys and pairing secret.

## Setup (both computers)

Open PowerShell in the project folder and run:

```powershell
uv sync
```

This creates a project-local `.venv` and installs the locked dependencies. You do not need to activate it; `uv run` uses it automatically. Install uv on each computer if needed: see [uv installation](https://docs.astral.sh/uv/getting-started/installation/).

## Start on the PC

```powershell
uv run python receiver.py
```

Keep the window open. It displays local IPv4 addresses, port, a certificate fingerprint, and a pairing secret. If several IPs are shown, choose the one belonging to the Ethernet adapter; run `ipconfig` if unsure. The first run generates `receiver-data` locally. Keep its contents private; it is excluded from Git.

If Windows Firewall asks, allow Python access to **private networks**. If the connection times out, check the machines are on the same local network and that the firewall permits inbound TCP port 45839 on the PC. Guest Wi-Fi or client isolation can prevent the devices from communicating.

## Start on the laptop

```powershell
uv run python controller.py
```

Enter the PC IP address, port, certificate fingerprint, and pairing secret shown on the PC. Check the fingerprint directly against the PC's display: it pins the receiver's certificate and protects the secret and input stream from an impersonator. Press **Connect**, then **PC**. Keyboard and mouse input now go to the PC. Press **Ctrl + Alt + Space** to return control to the laptop. Use the **Laptop** button when laptop control is active; the shortcut is needed while the PC has the mouse. Close either app or disconnect to return control to the laptop.

The shortcut releases forwarded keys and mouse buttons on the PC. If a connection fails, the receiver also releases inputs once it detects the disconnect. If control does not return immediately after an unexpected network failure, use Ctrl + Alt + Space; an ordinary TCP connection may take time to detect a cable or Wi-Fi failure.

## Security and limitations

- The connection uses TLS with a pinned, self-signed certificate and a randomly generated pairing secret. The secret grants control of the PC: share it only with trusted users. The listener binds to all local interfaces and accepts one connection at a time. Keep the PC on a trusted private network.
- The receiver-data folder contains the private key and secret. Delete it while the receiver is stopped to generate a new identity and secret. Copy the new fingerprint and secret to the laptop.
- This is a prototype. Windows secure screens, Ctrl+Alt+Delete, elevated application windows, some games and software that uses raw input may not accept forwarded input. Different keyboard layouts can affect characters. High-resolution scrolling may be coarse.
- The first version relies on Windows input hooks and simulated input, and does not stream a screen, share a clipboard, or automatically start with Windows. It needs a live interactive Windows session on each machine.
- Test the switch and shortcut with a second local mouse or keyboard available on the PC. The shortcut only works when the controller is running and Windows is accepting keyboard input.

