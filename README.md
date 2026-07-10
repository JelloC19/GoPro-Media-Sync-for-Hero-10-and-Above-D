
<img width="1014" height="705" alt="Screenshot 2026-07-10 130020" src="https://github.com/user-attachments/assets/c3c4f0ef-4521-4294-94f6-8bcdffffc2b0" />
<img width="1014" height="693" alt="Screenshot 2026-07-10 121951" src="https://github.com/user-attachments/assets/5d5ef053-9a60-4688-a11d-5fcd2a216bbe" />
<img width="1018" height="704" alt="Screenshot 2026-07-10 130622" src="https://github.com/user-attachments/assets/a1b94813-a835-45bd-82ab-8b867e53c836" />


# GoPro-Media-Sync-for-Hero-10-and-Above-D
This is what i would describe as a Pre Alpha its only Purpose is to Sync your gallery with the PC without you doing anything. 
Just open the install file wait for Python to install and then launch via the Shortcut :D 

GoPro Sync Pro
GoPro Sync Pro is a modern, lightweight desktop application built with Python and PySide6 for Windows. It aims to provide a more manageable way to connect your GoPro, view its hardware status, and synchronize your photos and videos to your local PC by working around some of the typical Windows MTP (Media Transfer Protocol) hiccups.

🌟 Why this tool?
Transferring large files from a GoPro via standard Windows MTP is notoriously flaky, prone to freezing, and often blocks hardware status queries. GoPro Sync Pro tackles this with a pragmatic hybrid approach: It reads the camera's battery level via Bluetooth Low Energy (BLE) to avoid stressing the USB connection, while handling file transfers through isolated PowerShell commands to keep the MTP pipeline from choking on large loops.

🚀 Key Features
Pragmatic Media Sync: Copies .mp4, .jpg, and .png files from the camera to a local folder. It includes a basic duplicate check to skip files that are already in the target directory.

BLE Battery Info: Uses a background BLE (Bluetooth) scan to fetch the battery percentage. This bypasses the MTP connection entirely, preventing the typical timeout freezes when asking the camera for its status.

Modern UI & Animations: A clean dark-mode interface with smooth CSS gradient animations, drop shadows, and customizable accent colors.

Built-in Media Galleries: Automatically generates thumbnails (powered by OpenCV) for synced media. Includes a functional video player and a simple photo viewer.

Real-time Progress: An animated overlay popup shows the currently transferring file and a rough ETA.

🛠️ Tech Stack
Python 3

PySide6 (Qt6) for the GUI and multimedia playback.

Bleak for asynchronous Bluetooth Low Energy communication.

OpenCV (cv2) for fast video thumbnail generation.

PowerShell & Shell.Application for executing isolated MTP file transfers.
