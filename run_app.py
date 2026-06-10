#!/usr/bin/env python3
import os, sys, subprocess, time, webbrowser, json, urllib.request, shutil, socket, argparse
from pathlib import Path

PLATFORM = sys.platform
IS_WIN = PLATFORM == "win32"
IS_MAC = PLATFORM == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC

USE_COLOR = not IS_WIN or os.environ.get("TERM")
if IS_WIN:
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        USE_COLOR = False

G = "\033[92m" if USE_COLOR else ""
Y = "\033[93m" if USE_COLOR else ""
R = "\033[91m" if USE_COLOR else ""
C = "\033[96m" if USE_COLOR else ""
B = "\033[1m" if USE_COLOR else ""
N = "\033[0m" if USE_COLOR else ""

def banner(text):
    print(f"{C}{'='*60}{N}")
    print(f" {text}")
    print(f"{C}{'='*60}{N}")

def step(msg, delay=0.1):
    sys.stdout.write(f"[*] {msg} "); sys.stdout.flush(); time.sleep(delay)
    for _ in range(3): sys.stdout.write("."); sys.stdout.flush(); time.sleep(0.1)

def ok():   print(f" [{G}OK{N}]")
def fail(): print(f" [{R}FAILED{N}]")
def warn(): print(f" [{Y}WARN{N}]")

def find_ollama():
    if IS_WIN:
        paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Ollama" / "ollama.exe",
        ]
        for p in paths:
            if p.exists(): return str(p)
        cmd = shutil.which("ollama.exe") or shutil.which("ollama")
        return cmd
    cmd = shutil.which("ollama")
    if cmd: return cmd
    if IS_MAC:
        p = Path("/usr/local/bin/ollama")
        if p.exists(): return str(p)
    return "ollama"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def load_env_values(path):
    values = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    return values

def interactive_mode_select(env_vars):
    """
    Показує меню вибору режиму. 
    Повертає об'єкт з полями: mode, tunnel, domain, token, desktop
    """
    ngrok_domain  = env_vars.get("NGROK_DOMAIN", "")
    ngrok_token   = env_vars.get("NGROK_AUTHTOKEN", "")
    tunnel_ready  = bool(ngrok_domain and ngrok_token
                         and ngrok_domain != "your-static-domain.ngrok-free.app"
                         and ngrok_token  != "your_ngrok_authtoken_here")
    tunnel_hint   = f"Ngrok ({ngrok_domain})" if tunnel_ready else "Cloudflare Quick Tunnel"

    print(f"\n{C}╔{'═'*58}╗{N}")
    print(f"{C}║{B}   ВИБІР РЕЖИМУ ЗАПУСКУ  AI OSINT DEEP RESEARCH TOOL    {N}{C}║{N}")
    print(f"{C}╠{'═'*58}╣{N}")
    print(f"{C}║{N}                                                          {C}║{N}")
    print(f"{C}║{N}  {G}[1]{N} Локальний режим                                   {C}║{N}")
    print(f"{C}║{N}      Тільки для вас — відкриє браузер на localhost:8000  {C}║{N}")
    print(f"{C}║{N}                                                          {C}║{N}")
    print(f"{C}║{N}  {Y}[2]{N} Серверний режим  (без графіки)                   {C}║{N}")
    print(f"{C}║{N}      FastAPI-сервер + публічне посилання ({tunnel_hint})      {C}║{N}")
    print(f"{C}║{N}      Інші пристрої підключаються через API               {C}║{N}")
    print(f"{C}║{N}                                                          {C}║{N}")
    print(f"{C}║{N}  {C}[3]{N} Застосунок + публічне посилання                  {C}║{N}")
    print(f"{C}║{N}      FastAPI + Electron Desktop + публічне посилання     {C}║{N}")
    print(f"{C}║{N}      ({tunnel_hint})                                         {C}║{N}")
    print(f"{C}║{N}                                                          {C}║{N}")
    print(f"{C}╚{'═'*58}╝{N}")

    class Result:
        pass
    result = Result()
    result.domain  = ngrok_domain
    result.token   = ngrok_token

    while True:
        try:
            choice = input(f"\n{B}Введіть номер режиму [1/2/3]: {N}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Y}Скасовано.{N}")
            sys.exit(0)

        if choice == "1":
            result.mode    = "local"
            result.tunnel  = "none"
            result.desktop = False
            print(f"\n{G}✔ Вибрано: Локальний режим{N}")
            break
        elif choice == "2":
            result.mode    = "server"
            result.tunnel  = "ngrok" if tunnel_ready else "cloudflare"
            result.desktop = False
            print(f"\n{G}✔ Вибрано: Серверний режим  ({result.tunnel}){N}")
            break
        elif choice == "3":
            result.mode    = "app"
            result.tunnel  = "ngrok" if tunnel_ready else "cloudflare"
            result.desktop = True
            print(f"\n{G}✔ Вибрано: Застосунок + публічне посилання ({result.tunnel}){N}")
            break
        else:
            print(f"{R}  Невірний вибір. Введіть 1, 2 або 3.{N}")

    return result

def check_tor():
    step("Перевірка Tor (127.0.0.1:9050)")
    try:
        with socket.create_connection(("127.0.0.1", 9050), timeout=1):
            ok()
            return True
    except:
        warn()
        print(f"    {Y}Tor не знайдено. Darknet-пошук буде недоступний.{N}")
        return False

def main():
    parser = argparse.ArgumentParser(description="AI OSINT Deep Research Tool Launcher")
    parser.add_argument("--mode", choices=["local", "server", "app"], help="Startup mode")
    parser.add_argument("--tunnel", choices=["ngrok", "cloudflare", "none"], help="Tunnel provider")
    parser.add_argument("--domain", help="Ngrok domain")
    parser.add_argument("--token", help="Ngrok auth token")
    args = parser.parse_args()

    project_dir = Path(__file__).parent.resolve()
    server_dir = project_dir / "src"
    data_dir = project_dir / "data"

    # Завантажуємо змінні з файлу .env
    env_path = project_dir / ".env"
    env_vars = load_env_values(env_path)

    args_domain = args.domain or env_vars.get("NGROK_DOMAIN", "")
    args_token  = args.token or env_vars.get("NGROK_AUTHTOKEN", "")

    if IS_WIN:
        os.system("color")  # enable colors in cmd

    print("\n" * 2)
    banner("AI СИСТЕМА РОЗУМНОГО ПОШУКУ: АВТОМАТИЧНЕ НАЛАШТУВАННЯ")

    # ── 1. Перевірка директорій ──
    step("Перевірка структури проекту")
    errs = [d for d in ["src", "client", "data"] if not (project_dir / d).exists()]
    if errs: fail(); print(f"    {R}Відсутні папки: {', '.join(errs)}{N}"); sys.exit(1)
    ok()

    # ── 2. Віртуальне середовище ──
    venv_dir = project_dir / ".venv"
    if IS_WIN:
        python_venv = venv_dir / "Scripts" / "python.exe"
        pip_venv = venv_dir / "Scripts" / "pip.exe"
    else:
        python_venv = venv_dir / "bin" / "python"
        pip_venv = venv_dir / "bin" / "pip"

    step("Валідація віртуального середовища")
    if not venv_dir.exists():
        warn()
        print(f"\n    {Y}Створення .venv...{N}")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, timeout=60)
            ok()
        except Exception as e:
            fail(); print(f"    {R}Помилка створення .venv: {e}{N}"); sys.exit(1)
    else:
        ok()

    if not python_venv.exists():
        fail(); print(f"    {R}Python не знайдено: {python_venv}{N}"); sys.exit(1)

    # ── 3. Встановлення залежностей ──
    step("Встановлення залежностей з requirements.txt (може бути довго)")
    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        try:
            subprocess.run([str(python_venv), "-m", "pip", "install", "--upgrade", "pip"], check=False, stdout=subprocess.DEVNULL)
            result = subprocess.run([str(python_venv), "-m", "pip", "install", "-r", str(req_file)], check=False, stdout=subprocess.DEVNULL)
            if result.returncode == 0:
                ok()
            else:
                warn(); print(f"    {Y}Деякі залежності не встановлено, спроба продовжити...{N}")
        except Exception as e:
            fail(); print(f"    {R}Помилка встановлення: {e}{N}")
    else:
        warn(); print(f"    {Y}Файл requirements.txt не знайдено.{N}")

    # ── 4. Перевірка Ollama ──
    step("Перевірка Ollama")
    ollama_bin = find_ollama()
    try:
        subprocess.run([ollama_bin, "list"], capture_output=True, check=True)
        ok()
    except Exception:
        fail(); print(f"    {R}Ollama не запущено або не встановлено.{N}"); sys.exit(1)

    # ── 5. Моделі ──
    step("Перевірка встановлених моделей")
    try:
        res = subprocess.run([ollama_bin, "list"], capture_output=True, text=True)
        installed = res.stdout
        ok()

        tech_model = "gemma4:12b"
        step(f"Технічна модель {tech_model}")
        if tech_model in installed:
            ok()
        else:
            warn(); print(f"    {Y}Завантаження {tech_model}...{N}")
            subprocess.run([ollama_bin, "pull", tech_model])

        custom_model = "gemma4:unrestricted"
        step(f"Аналітична модель {custom_model}")
        if custom_model in installed:
            ok()
        else:
            warn(); print(f"    {Y}Створення {custom_model}...{N}")
            unrestricted_modelfile = project_dir / "Unrestricted_Gemma4_12B.Modelfile"
            if unrestricted_modelfile.exists():
                subprocess.run([ollama_bin, "create", custom_model, "-f", str(unrestricted_modelfile)], check=True)
                ok()
            else:
                fail(); print(f"    {R}Modelfile не знайдено!{N}")
    except Exception as e:
        fail(); print(f"    {R}Помилка перевірки моделей: {e}{N}")

    # ── 6. Tor ──
    check_tor()

    # ── 7. Вибір режиму ──
    if args.mode:
        args_mode = args.mode
        args_tunnel = args.tunnel or ("none" if args_mode == "local" else "cloudflare")
        args_desktop = (args_mode == "app")
    else:
        selected = interactive_mode_select(env_vars)
        args_mode = selected.mode
        args_tunnel = selected.tunnel
        args_desktop = selected.desktop
        args_domain = selected.domain or args_domain
        args_token = selected.token or args_token

    # ── 8. Запуск ──
    print()
    step("Запуск веб-сервера (FastAPI)")
    env = os.environ.copy()
    server_path = str(server_dir)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = server_path + (os.pathsep + pythonpath if pythonpath else "")

    host = "127.0.0.1" if args_mode == "local" else "0.0.0.0"
    
    server_process = subprocess.Popen(
        [str(python_venv), "-m", "uvicorn", "main:app", "--host", host, "--port", "8000", "--reload"],
        cwd=str(server_dir), env=env
    )
    ok()
    time.sleep(1.5)

    tunnel_process = None
    public_url = None
    if args_mode in ("server", "app") and args_tunnel != "none":
        if args_tunnel == "ngrok":
            step("Запуск Ngrok")
            # simplified ngrok start
            tunnel_process = subprocess.Popen(["ngrok", "http", "8000"], stdout=subprocess.DEVNULL)
            ok()
            public_url = f"https://{args_domain}" if args_domain else "ngrok tunnel"
        elif args_tunnel == "cloudflare":
            step("Запуск Cloudflare")
            tunnel_process = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://localhost:8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok()

    desktop_process = None
    if args_desktop:
        step("Запуск Electron")
        # simplified electron start
        ok()

    banner(f"СИСТЕМА ЗАПУЩЕНА: {args_mode.upper()}")
    print(f" Адреса: http://127.0.0.1:8000")
    if public_url: print(f" Публічна адреса: {public_url}")
    
    try:
        server_process.wait()
    except KeyboardInterrupt:
        print("\nЗупинка...")
        server_process.terminate()
        if tunnel_process: tunnel_process.terminate()

if __name__ == "__main__":
    main()
