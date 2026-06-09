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
        mac_paths = [
            "/Applications/Ollama.app/Contents/Resources/ollama",
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
        ]
        for p in mac_paths:
            if os.path.exists(p): return p
    return "ollama"

def wait_for_ollama(url, timeout=15):
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200: return True
        except Exception: pass
        time.sleep(1)
    return False

def pull_model(model_name):
    step(f"Завантаження моделі {model_name} (це може тривати хвилини...)")
    sys.stdout.flush()
    ollama = find_ollama()
    try:
        r = subprocess.run([ollama, "pull", model_name], capture_output=True, text=True, timeout=600)
        if r.returncode == 0: ok(); return True
        print(f"\n{Y}stdout: {r.stdout[:200]}{N}")
        print(f"{Y}stderr: {r.stderr[:200]}{N}")
        warn(); return False
    except subprocess.TimeoutExpired:
        warn(); print(f"\n    {Y}Timeout – модель може бути великою, спробуйте вручну: ollama pull {model_name}{N}")
        return False
    except Exception as e:
        warn(); print(f"\n    {Y}Помилка: {e}{N}")
        return False

def create_custom_model(base, custom, modelfile_path):
    step(f"Створення моделі {custom} з {base}")
    sys.stdout.flush()
    if not modelfile_path.exists():
        warn()
        print(f"\n    {Y}Modelfile не знайдено: {modelfile_path}{N}")
        return False
    ollama = find_ollama()
    with open(modelfile_path) as f:
        modelfile_content = f.read()
    try:
        r = subprocess.run(
            [ollama, "create", custom],
            input=modelfile_content, capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0: ok(); return True
        warn(); print(f"\n    {Y}Помилка: {r.stderr[:200]}{N}")
        return False
    except Exception as e:
        warn(); print(f"\n    {Y}Помилка: {e}{N}")
        return False

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def load_env_values(env_path):
    env_vars = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        val = val.strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        env_vars[key.strip()] = val
        except Exception:
            pass
    return env_vars

def interactive_mode_select(env_vars):
    """
    Показує красиве інтерактивне меню вибору режиму запуску.
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
        s = socket.socket()
        s.settimeout(1)
        s.connect(('127.0.0.1', 9050))
        s.close()
        ok()
        return True
    except:
        warn()
        print(f"    {Y}Tor не знайдено. Darknet-пошук буде недоступний.{N}")
        return False

def main():
    project_dir = Path(__file__).parent.resolve()
    server_dir = project_dir / "src"
    data_dir = project_dir / "data"
    unrestricted_modelfile = project_dir / "Modelfile_Dolphin"

    # Завантажуємо змінні з файлу .env
    env_path = project_dir / ".env"
    env_vars = load_env_values(env_path)

    # Зчитуємо тільки параметри підключення з .env — режим буде запитано після калібрування
    args_domain = env_vars.get("NGROK_DOMAIN", "")
    args_token  = env_vars.get("NGROK_AUTHTOKEN", "")
    # args.mode буде встановлено після завершення перевірок системи (крок 6)

    if IS_WIN:
        os.system("color")  # enable colors in cmd

    print("\n" * 2)
    banner("AI СИСТЕМА РОЗУМНОГО ПОШУКУ: АВТОМАТИЧНЕ НАЛАШТУВАННЯ")

    # ── 1. Перевірка директорій ──
    step("Перевірка структури проекту")
    errs = [d for d in ["server", "client", "data"] if not (project_dir / d).exists()]
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
            print(f"\n{C}--- Прогрес встановлення pip ---{N}")
            # Показуємо вивід pip користувачу, щоб було видно прогрес
            subprocess.run([str(python_venv), "-m", "pip", "install", "--upgrade", "pip"], check=False)
            result = subprocess.run([str(python_venv), "-m", "pip", "install", "-r", str(req_file)], 
                                     check=False)
            if result.returncode == 0:
                ok()
            else:
                warn()
                print(f"    {Y}Деякі залежності могли не встановитись. Спробуйте вручну: pip install -r requirements.txt{N}")
        except Exception as e:
            warn(); print(f"\n    {Y}Помилка: {e}{N}")
    else:
        warn(); print(f"\n    {Y}requirements.txt не знайдено{N}")

    # ── 4. Ollama ──
    step("Перевірка Ollama")
    ollama = find_ollama()
    ollama_online = wait_for_ollama("http://localhost:11434", timeout=2)

    if not ollama_online:
        warn()
        print(f"\n    {Y}Ollama не запущена. Спроба автоматичного запуску...{N}")
        try:
            if IS_WIN:
                subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif IS_MAC:
                subprocess.Popen(["open", "-a", "Ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            step("Очікування запуску Ollama", delay=0.5)
            ollama_online = wait_for_ollama("http://localhost:11434", timeout=10)
            if ollama_online: ok()
            else: fail(); print(f"    {Y}Не вдалося запустити – перейдіть у Search-Only режим{N}")
        except Exception as e:
            fail(); print(f"    {Y}Помилка запуску: {e}{N}")
    else:
        ok()

    # ── 5. Моделі ──
    if ollama_online:
        step("Перевірка встановлених моделей")
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as r:
                tags = json.loads(r.read().decode())["models"]
                installed = [m["name"] for m in tags]
                ok()
        except Exception:
            installed = []
            warn()

        # Список моделей для гібридного режиму
        # 1. Технічна модель (Gemma 4 12B)
        tech_model = "gemma4:12b"
        if any(tech_model in m for m in installed):
            step(f"Технічна модель {tech_model}")
            ok()
        else:
            pull_model(tech_model)

        # 2. Модель для аналізу (Безцензурна)
        base_dolphin = "gemma4:12b"
        custom_dolphin = "gemma4:unrestricted"
        unrestricted_modelfile = project_dir / "Unrestricted_Gemma4_12B.Modelfile"
        
        has_base_dolphin = any(base_dolphin in m for m in installed)
        has_custom_dolphin = any(custom_dolphin in m for m in installed)

        if not has_base_dolphin and not has_custom_dolphin:
            pull_model(base_dolphin)
            has_base_dolphin = True

        if has_custom_dolphin:
            step(f"Аналітична модель {custom_dolphin}")
            ok()
        else:
            create_custom_model(base_dolphin, custom_dolphin, unrestricted_modelfile)

    # ── 6. Tor ──
    check_tor()

    # ── 7. Вибір режиму запуску ──
    selected = interactive_mode_select(env_vars)
    args_mode    = selected.mode
    args_tunnel  = selected.tunnel
    args_desktop = selected.desktop
    if not args_domain:
        args_domain = selected.domain
    if not args_token:
        args_token = selected.token

    # ── 7. Запуск сервера ──
    print()
    step("Запуск веб-сервера (FastAPI)")
    env = os.environ.copy()
    server_path = str(server_dir)
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = server_path + (os.pathsep + pythonpath if pythonpath else "")

    # Окремі процеси, які ми запустимо
    server_process = None
    tunnel_process = None
    desktop_process = None

    try:
        # Режим 1 (local)  → 127.0.0.1  — тільки localhost, відкриває браузер
        # Режим 2 (server) → 0.0.0.0    — headless API + публічний тунель
        # Режим 3 (app)    → 0.0.0.0    — Electron Desktop + публічний тунель
        host = "127.0.0.1" if args_mode == "local" else "0.0.0.0"

        server_process = subprocess.Popen(
            [str(python_venv), "-m", "uvicorn", "main:app", "--host", host, "--port", "8000", "--reload"],
            cwd=str(server_dir), env=env
        )
        ok()
        time.sleep(1.5)

        # ── Публічний тунель (тільки для режимів 2 і 3) ──
        public_url = None
        if args_mode in ("server", "app") and args_tunnel and args_tunnel != "none":

            if args_tunnel == "ngrok":
                step("Запуск публічного тунелю Ngrok")
                if args_token:
                    try:
                        subprocess.run(["ngrok", "config", "add-authtoken", args_token],
                                       capture_output=True, text=True, timeout=10)
                    except Exception:
                        try:
                            subprocess.run(["npx", "ngrok", "config", "add-authtoken", args_token],
                                           capture_output=True, text=True, timeout=15)
                        except Exception:
                            pass

                ngrok_cmd = ["ngrok", "http"]
                if args_domain:
                    ngrok_cmd.append(f"--domain={args_domain}")
                ngrok_cmd.append("8000")

                try:
                    tunnel_process = subprocess.Popen(ngrok_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    try:
                        npx_cmd = ["npx", "ngrok", "http"]
                        if args_domain:
                            npx_cmd.append(f"--domain={args_domain}")
                        npx_cmd.append("8000")
                        tunnel_process = subprocess.Popen(npx_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception as e:
                        warn()
                        print(f"    {Y}Не вдалося запустити Ngrok: {e}{N}")

                if tunnel_process:
                    ok()
                    public_url = f"https://{args_domain}" if args_domain else "[перевірте ngrok dashboard]"

            elif args_tunnel == "cloudflare":
                step("Запуск Cloudflare Quick Tunnel")
                try:
                    cf_cmd = shutil.which("cloudflared") or "cloudflared"
                    tunnel_process = subprocess.Popen(
                        [cf_cmd, "tunnel", "--url", "http://127.0.0.1:8000"]
                    )
                except Exception:
                    try:
                        npx_cmd = shutil.which("npx") or "npx"
                        tunnel_process = subprocess.Popen(
                            [npx_cmd, "-y", "cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"]
                        )
                    except Exception as e:
                        warn()
                        print(f"    {Y}Не вдалося запустити Cloudflare Tunnel: {e}{N}")
                if tunnel_process:
                    ok()
                    public_url = "[Cloudflare Quick Tunnel URL — дивіться вікно cloudflared]"

        # ── Запуск клієнта ──
        if args_mode == "local":
            # Режим 1: просто відкриваємо браузер
            webbrowser.open("http://127.0.0.1:8000")

        elif args_mode == "app":
            # Режим 3: запускаємо Electron Desktop
            electron_dir = project_dir / "electron_client"
            if electron_dir.exists():
                step("Запуск Electron Desktop-застосунку")
                node_modules = electron_dir / "node_modules"
                if not node_modules.exists():
                    print(f"\n    {Y}node_modules не знайдено. Встановлення npm-залежностей...{N}")
                    npm_cmd = shutil.which("npm") or "npm"
                    try:
                        subprocess.run([npm_cmd, "install"], cwd=str(electron_dir), check=True, timeout=180)
                    except Exception as e:
                        print(f"    {R}npm install помилка: {e}{N}")
                try:
                    npm_cmd = shutil.which("npm") or "npm"
                    desktop_process = subprocess.Popen(
                        [npm_cmd, "start"], cwd=str(electron_dir),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    ok()
                except Exception as e:
                    warn()
                    print(f"    {Y}Не вдалося запустити Electron: {e}{N}")
            else:
                print(f"    {Y}Папка electron_client не знайдена в проекті!{N}")

        # ── Фінальна інформаційна панель ──
        mode_labels = {
            "local":  "ВИКЛЮЧНО ДЛЯ МЕНЕ    — браузер на localhost:8000",
            "server": "ВИКЛЮЧНО ДЛЯ ІНШИХ   — headless API + публічне посилання",
            "app":    "КОМБІНОВАНИЙ РЕЖИМ   — Electron Desktop + публічне посилання",
        }
        print(f"\n{G}{'='*60}{N}")
        print(f" {G}СИСТЕМА ЗАПУЩЕНА: {mode_labels.get(args_mode, args_mode)}{N}")
        print(f" {C}Адреса (localhost): {N} {B}http://127.0.0.1:8000{N}")

        if args_mode in ("server", "app"):
            local_ip = get_local_ip()
            print(f" {C}Адреса (мережа):   {N} {B}http://{local_ip}:8000{N}")

        if public_url:
            print(f" {C}Публічне посилання:{N} {B}{public_url}{N}")
        elif args_mode in ("server", "app") and args_tunnel == "none":
            print(f" {Y}Тунель не активний. Для публічного посилання налаштуйте Ngrok у .env{N}")

        print(f"  [Ctrl+C] для зупинки всіх процесів")
        print(f"{G}{'='*60}{N}\n")

        server_process.wait()

    except KeyboardInterrupt:
        print(f"\n{Y}Зупинка всіх процесів...{N}")
        
        # Гасимо всі підпроцеси
        for p_name, proc in [("Сервер", server_process), ("Публічний тунель", tunnel_process), ("Electron-застосунок", desktop_process)]:
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        
        print(f"{G}Всі процеси успішно зупинено. Систему вимкнено.{N}")
        
    except Exception as e:
        print(f"\n{R}Критична помилка під час роботи: {e}{N}")
        # Переконуємось, що процеси не зависнуть
        for proc in [server_process, tunnel_process, desktop_process]:
            if proc:
                try: proc.kill()
                except Exception: pass
        sys.exit(1)

if __name__ == "__main__":
    main()
