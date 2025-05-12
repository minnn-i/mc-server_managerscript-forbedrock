import os
import re
import time
import threading
import subprocess
import zipfile
import sys
import datetime
from mcstatus import BedrockServer # type: ignore
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# 📁 Paths
WORLD_NAME = "Umbrachain"
WORLD_PATH = f"./worlds/{WORLD_NAME}"
BACKUP_FOLDER = "backups"
LOG_DIR = "logs"
LOG_HISTORY_FILE = os.path.join(LOG_DIR, "server_history.log")


# ⏱️ Configurable settings
RESTART_COUNTDOWN_SECONDS = 120
SHUTDOWN_COUNTDOWN_SECONDS = 120
IDLE_TIME_LIMIT = 3600  # 1 hour

# 🚩 Global flags
CANCEL_FLAG = threading.Event()
countdown_cancelled = False

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 👨‍📸 Logging function
def log(message, is_history=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    if is_history:
        with open(LOG_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(full_message + "\n")

# 🎨 Format log lines
def format_log_line(line):
    if re.search(r"\[.*ERROR.*\]", line):
        return Fore.LIGHTRED_EX + Style.BRIGHT + line
    elif re.search(r"\[.*WARN.*\]", line):
        return Fore.LIGHTYELLOW_EX + Style.BRIGHT + line
    elif re.search(r"Player connected", line):
        return Fore.LIGHTGREEN_EX + Style.BRIGHT + line
    elif re.search(r"Player Spawned", line):
        return Fore.CYAN + Style.BRIGHT + line
    elif re.search(r"Player disconnected", line):
        return Fore.LIGHTMAGENTA_EX + Style.BRIGHT + line
    elif "Server started" in line:
        return Fore.GREEN + Style.BRIGHT + line
    else:
        return Style.BRIGHT + line

# 🎮 Send command to server via stdin
def send_command(process, command):
    try:
        if process and process.stdin:
            encoded = (command + "\n").encode("cp1252", errors="replace")
            process.stdin.write(encoded)
            process.stdin.flush()
            log(Fore.LIGHTWHITE_EX + f"[CMD] > {command}")
        else:
            log(Fore.LIGHTRED_EX + "[ERROR] Server process not available.")
    except Exception as e:
        log(Fore.LIGHTRED_EX + f"[ERROR] Failed to send command: {e}")

# 💾 Backup world folder
def backup_world():
    try:
        if not os.path.exists(WORLD_PATH):
            log(f"[ERROR] World folder not found: {WORLD_PATH}", Fore.LIGHTRED_EX)
            return False

        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        zip_name = f"{WORLD_NAME}_backup_{timestamp}.zip"
        zip_path = os.path.join(BACKUP_FOLDER, zip_name)

        log(f"[BACKUP] Backing up world: {WORLD_NAME}", Fore.YELLOW)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(WORLD_PATH):
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, os.path.dirname(WORLD_PATH))
                    zipf.write(filepath, arcname)

        MAX_BACKUPS = 10
        backups = sorted(
            [f for f in os.listdir(BACKUP_FOLDER) if f.endswith(".zip")]
        )
        if len(backups) > MAX_BACKUPS:
            to_delete = backups[0:len(backups) - MAX_BACKUPS]
            for old in to_delete:
                os.remove(os.path.join(BACKUP_FOLDER, old))
                log(f"[CLEANUP] Old backup deleted: {old}", Fore.LIGHTBLACK_EX)

        log(Style.BRIGHT + Fore.GREEN + f"[SUCCESS] Backup completed: {zip_name}")
        return True

    except Exception as e:
        log(Fore.LIGHTRED_EX + f"[ERROR] Backup failed: {e}")
        return False


# 🔁 Restart server with countdown
def restart_command(process, player="Console"):
    global countdown_cancelled
    CANCEL_FLAG.clear()
    countdown_cancelled = False
    log(Fore.LIGHTRED_EX + f"[ADMIN] Warning Restart command issued by {player}.")
    try:
        # Notify players to wait for backup before restarting
        send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§e[Server] Please wait for the server backup before restarting..."}]}')
        log(Fore.YELLOW + "[Server] Please wait for the server backup before restarting...")

        send_command(process, 'save hold')
        time.sleep(1)
        send_command(process, 'save query')
        time.sleep(2)

        send_command(process, 'save resume')

        if backup_world():
            send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§a[Backup] Backup completed. Restart countdown begins in 3 seconds..."}]}')
            send_command(process, 'playsound random.orb @a')
            log(Fore.LIGHTGREEN_EX + Style.BRIGHT + "[Server] Backup completed. Restart countdown begins in 3 seconds...")
            time.sleep(3)

            for i in range(RESTART_COUNTDOWN_SECONDS, 0, -1):
                # Check if cancel flag is set
                if CANCEL_FLAG.is_set():
                    send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§a[Server] Restart cancelled!"}]}')
                    log(Style.BRIGHT + Fore.LIGHTYELLOW_EX + "[Server] Restart cancelled.")
                    return
                if i in [120, 60, 30, 10, 5, 3, 2, 1]:
                    send_command(process, f'tellraw @a {{"rawtext":[{{"text":"§l§e[Server] Restarting in {i} seconds..."}}]}}')
                    log(Fore.LIGHTYELLOW_EX + Style.BRIGHT + f"[Server] Restarting in {i} seconds...")
                if i in [3, 2, 1]:
                    send_command(process, "playsound note.pling @a")
                time.sleep(1)

            log(Style.BRIGHT + "[Server] Restarting server...", is_history=True)
            send_command(process, "stop")
            time.sleep(2)  # แก้ไขการรอให้เซิร์ฟเวอร์หยุดเล็กน้อยก่อน restart
            start_server()  # เรียกใช้งานฟังก์ชันเริ่มเซิร์ฟเวอร์ใหม่
        else:
            send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§c[Backup] Backup failed. Restart canceled."}]}')
            log(Fore.LIGHTRED_EX + "[Backup] Backup failed. Restart canceled.")
    except Exception as e:
        send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§c[Server] Restart failed."}]}')
        log(Fore.LIGHTRED_EX + f"[ERROR] Restart failed: {e}")

# 🔒 Shutdown server with countdown
def shutdown_command(process, player="Console"):
    global countdown_cancelled
    CANCEL_FLAG.clear()
    countdown_cancelled = False
    log(Fore.LIGHTRED_EX + f"[ADMIN] Warning Shutdown command issued by {player}.")
    try:
        # Notify players to wait for backup before shutting down
        send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§e[Server] Please wait for the server backup before shutting down..."}]}')
        log(Fore.YELLOW + "[Server] Please wait for the server backup before shutting down...")

        send_command(process, 'save hold')
        time.sleep(1)
        send_command(process, 'save query')
        time.sleep(2)
        
        send_command(process, 'save resume')

        if backup_world():
            send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§a[Backup] Backup completed. Shutdown countdown begins in 3 seconds..."}]}')
            send_command(process, 'playsound random.orb @a')
            log(Fore.LIGHTGREEN_EX + Style.BRIGHT + "[Server] Backup completed. Shutdown countdown begins in 3 seconds...")
            time.sleep(3)

            for i in range(SHUTDOWN_COUNTDOWN_SECONDS, 0, -1):
                # Check if cancel flag is set
                if CANCEL_FLAG.is_set():
                    send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§a[Server] Shutdown cancelled!"}]}')
                    log(Style.BRIGHT + Fore.LIGHTYELLOW_EX + "[Server] Shutdown cancelled.")
                    return
                if i in [120, 60, 30, 10, 5, 3, 2, 1]:
                    send_command(process, f'tellraw @a {{"rawtext":[{{"text":"§l§e[Server] Shutting down in {i} seconds..."}}]}}')
                    log(Fore.LIGHTYELLOW_EX + Style.BRIGHT + f"[Server] Shutting down in {i} seconds...")
                if i in [3, 2, 1]:
                    send_command(process, "playsound note.pling @a")
                time.sleep(1)

            log(Style.BRIGHT + "[Server] Shutting down server...", is_history=True)
            send_command(process, "stop")
            time.sleep(2)  # แก้ไขการรอให้เซิร์ฟเวอร์หยุดเล็กน้อยก่อน shutdown
        else:
            send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§c[Backup] Backup failed. Shutdown canceled."}]}')
            log(Fore.LIGHTRED_EX + "[Backup] Backup failed. Shutdown canceled.")
    except Exception as e:
        send_command(process, 'tellraw @a {"rawtext":[{"text":"§l§c[Server] Shutdown failed."}]}')
        log(Fore.LIGHTRED_EX + f"[ERROR] Shutdown failed: {e}")




# 🌐 Get player count using mcstatus
def get_online_player_count(host="localhost", port=19132):
    try:
        server = BedrockServer.lookup(f"{host}:{port}")
        status = server.status()
        return status.players.online
    except Exception as e:
        log(f"[ERROR] mcstatus query failed: {e}", Fore.LIGHTRED_EX)
        return None


# 🛌 Idle Monitor: ตรวจจับสถานะไม่มีผู้เล่นออนไลน์และรีสตาร์ทอัตโนมัติ
def idle_monitor(process):
    current_idle_limit = IDLE_TIME_LIMIT
    last_active_time = time.time()
    was_empty = False
    log_file_path = os.path.join(os.getcwd(), "logs", "latest.log")
    

    while True:
        time.sleep(120)
        try:
            count = get_online_player_count()
            if count is None:
                continue  # ถ้า query fail ก็ข้ามรอบนี้

            if count == 0:
                if not was_empty:
                    was_empty = True
                    last_active_time = time.time()
                    log(Fore.LIGHTYELLOW_EX + "No players online. Idle timer started.")
                if time.time() - last_active_time >= current_idle_limit:
                    log(Fore.LIGHTRED_EX + "\U0001F4A4 Server is idle. Restarting...")
                    restart_command(process)
                    current_idle_limit += 3600  # ยืดเวลา idle ไปอีกชั่วโมง
            else:
                if was_empty:
                    log(Fore.LIGHTCYAN_EX + "\U0001F3AE Player joined. Idle timer reset.")
                was_empty = False
                current_idle_limit = IDLE_TIME_LIMIT
                last_active_time = time.time()
        except Exception as e:
            log(Fore.LIGHTRED_EX + f"[ERROR] Idle monitor failed: {e}")


def wait_for_input(process):
    log(Fore.LIGHTCYAN_EX + "[DEBUG] wait_for_input started")  # เช็คว่า thread นี้รันจริง
    while True:
        try:
            command = input(Fore.LIGHTWHITE_EX + "> " + Style.RESET_ALL).strip().lower()
            log(Fore.LIGHTCYAN_EX + f"[DEBUG] Got input: {command}")  # ดูว่า input ตอบสนองหรือไม่
        except Exception as e:
            log(Fore.LIGHTRED_EX + f"[ERROR] input failed: {e}")
            break

        if command == "restart":
            restart_command(process)
        elif command == "cancel":
            CANCEL_FLAG.set()
        elif command == "shutdown":
            shutdown_command(process)
        elif command == "backup":
            backup_world()
        elif command == "players":
            send_command(process, "list")
        elif command == "exit":
            log("[INFO] Exiting program.")
            break


# 🔧 Main Tail logs
def tail_log_file():
    log_path = os.path.join("logs", "latest.log")
    while not os.path.exists(log_path):
        time.sleep(0.5)
    with open(log_path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                log(format_log_line(line.strip()))
            else:
                time.sleep(0.1)



# 🔧 Main server function
def start_server():
    try:
        log(Fore.LIGHTGREEN_EX + "[INFO] Starting server...")
        process = subprocess.Popen(
            ["bedrock_server.exe"], cwd=os.getcwd(), stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        log(Fore.GREEN + "[INFO] Server started.")

        # Start background threads
        threading.Thread(target=idle_monitor, args=(process,), daemon=True).start()
        threading.Thread(target=wait_for_input, args=(process,), daemon=True).start()
        threading.Thread(target=tail_log_file, daemon=True).start()

        # Wait for the process to finish
        process.wait()
        log(Fore.LIGHTYELLOW_EX + "[INFO] Server process has terminated.")
        log(Fore.LIGHTYELLOW_EX + "[INFO] Server process exited.")
    except Exception as e:
        log(Fore.LIGHTRED_EX + f"[ERROR] Failed to start server: {e}")
    input("Press Enter to exit...")


if __name__ == "__main__":
    try:
        start_server()
    except Exception as e:
        log(Fore.LIGHTRED_EX + f"[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
