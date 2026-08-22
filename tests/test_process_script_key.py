"""Script identity for replacing messenger process pins."""

from core.runtime.process_script_key import process_script_key


def test_same_python_script_same_key() -> None:
    a = process_script_key("python3 app.py --port 8000")
    b = process_script_key("python app.py --reload")
    assert a == b == "app.py"


def test_different_scripts_different_keys() -> None:
    assert process_script_key("python bot.py") != process_script_key("python worker.py")


def test_npm_run_scripts() -> None:
    assert process_script_key("npm run dev") != process_script_key("npm run start")
    assert process_script_key("npm run dev -- --port 3000") == "npm:dev"


def test_python_module_and_uvicorn() -> None:
    assert process_script_key("python -m http.server 8080") == "py-m:http.server"
    assert process_script_key("uvicorn app.main:app --reload") == "asgi:app.main:app"


def test_cwd_disambiguates() -> None:
    a = process_script_key("python app.py", cwd="/tmp/one")
    b = process_script_key("python app.py", cwd="/tmp/two")
    assert a != b
    assert a.endswith("::app.py")
