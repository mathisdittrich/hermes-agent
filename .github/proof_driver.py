"""Live proof: Desktop's source update check on a fresh Windows source install with no system Git.

Installs Hermes with the real install.ps1 at BRANCH/COMMIT, hides every system Git from PATH (a
machine without Git for Windows), then runs the exact argv Desktop's readSourceUpdate spawns
(installed launcher, --run-module hermes_cli.source_check, --git git: what resolveGitBinary
returns when it finds no git). Also runs `hermes update --check` on the same PATH for contrast.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import urllib.request

BRANCH, COMMIT, LEG = sys.argv[1], sys.argv[2], sys.argv[3]
LAD = os.environ["LOCALAPPDATA"]
HH = os.path.join(LAD, "hermes")
ROOT = os.path.join(HH, "hermes-agent")
SCRATCH = os.environ.get("RUNNER_TEMP") or os.path.join(LAD, "Temp")


def clean_env():
    env = {}
    for key, value in os.environ.items():
        if key.upper() == "PSMODULEPATH":
            continue
        if key.upper() == "PATH":
            value = os.pathsep.join(p for p in value.split(os.pathsep)
                                    if p and "\\git" not in p.lower() and "/git" not in p.lower())
        env[key] = value
    return env


def path_of(env):
    return next(v for k, v in env.items() if k.upper() == "PATH")


env = clean_env()
print(f"[{LEG}] git on stripped PATH:", shutil.which("git", path=path_of(env)))

script = os.path.join(SCRATCH, "install.ps1")
urllib.request.urlretrieve(f"https://raw.githubusercontent.com/NousResearch/hermes-agent/{COMMIT}/scripts/install.ps1", script)
install = subprocess.run(
    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
     "-Branch", BRANCH, "-Commit", COMMIT, "-NonInteractive", "-SkipSetup", "-SkipBrowser", "-SkipComputerUse"],
    env=env, stdin=subprocess.DEVNULL, timeout=2400)
print(f"[{LEG}] install.ps1 exit:", install.returncode)
if install.returncode:
    sys.exit(f"install failed ({install.returncode})")

head = subprocess.run([glob.glob(os.path.join(HH, "tools", "git-*", "cmd", "git.exe"))[0], "-C", ROOT, "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout.strip()
print(f"[{LEG}] installed HEAD:", head)
print(f"[{LEG}] store git entries:", glob.glob(os.path.join(HH, "tools", "git-*")))
print(f"[{LEG}] git on stripped PATH after install:", shutil.which("git", path=path_of(env)))

launcher = next(p for p in (os.path.join(ROOT, ".hermes", "bin", "hermes.exe"), os.path.join(HH, "bin", "hermes.exe"))
                if os.path.isfile(p))
print(f"[{LEG}] launcher:", launcher)

# Desktop's sourceUpdateEnvironment: process env + HERMES_HOME + HERMES_INSTALL_ROOT, no HERMES_RUNTIME_DIR.
desk_env = dict(env, HERMES_HOME=HH, HERMES_INSTALL_ROOT=ROOT, PYTHONPATH="", PYTHONHOME="", PYTHONUTF8="1")
desk_env.pop("HERMES_RUNTIME_DIR", None)
argv = [launcher, "--run-module", "hermes_cli.source_check", "--install-root", ROOT, "--home", HH,
        "--git", "git", "--force"]
check = subprocess.run(argv, cwd=ROOT, env=desk_env, capture_output=True, text=True, encoding="utf-8", timeout=360)
print(f"[{LEG}] desktop source check exit:", check.returncode)
print(f"[{LEG}] desktop source check stdout:", check.stdout.strip())
if check.stderr.strip():
    print(f"[{LEG}] desktop source check stderr (tail):", check.stderr.strip()[-1500:])
status = json.loads(check.stdout)

cli = subprocess.run([launcher, "update", "--check"], cwd=ROOT, env=dict(env, HERMES_HOME=HH),
                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
print(f"[{LEG}] hermes update --check exit:", cli.returncode)
print(f"[{LEG}] hermes update --check output (tail):", (cli.stdout + cli.stderr).strip()[-1200:])

verdict = {"leg": LEG, "error": status.get("error"), "message": status.get("message"),
           "currentSha": status.get("currentSha"), "installedHead": head, "behind": status.get("behind")}
print("VERDICT", json.dumps(verdict))
with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
    fh.write(f"### {LEG}\n```\n{json.dumps(verdict, indent=1)}\n```\n")
