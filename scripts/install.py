#!/usr/bin/env python3
"""
Bootstrap da instalação do Foreguard — usa só a biblioteca padrão.

    python3 scripts/install.py [opções de `foreguard install`]

Cria venv/ na raiz do repositório (se não existir), instala o pacote nele e
executa `foreguard install`, repassando os argumentos.
"""
import os
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 12)
ROOT = Path(__file__).resolve().parent.parent


def python_supported(version) -> bool:
    return tuple(version[:2]) >= MIN_PYTHON


def venv_python(venv_dir: Path, os_name: str = os.name) -> Path:
    if os_name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not python_supported(sys.version_info):
        print(f"O Foreguard requer Python {'.'.join(map(str, MIN_PYTHON))} ou superior "
              f"(encontrado {sys.version.split()[0]}).", file=sys.stderr)
        return 1

    venv_dir = ROOT / "venv"
    if not venv_dir.exists():
        print(f"Criando ambiente virtual em {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    python = venv_python(venv_dir)
    print("Instalando o Foreguard e dependências...")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(ROOT)], check=True)

    return subprocess.call([str(python), "-m", "foreguard", "install", *argv], cwd=ROOT)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Falha ao executar: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
    except KeyboardInterrupt:
        sys.exit(130)
