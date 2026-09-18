# Contributing

Thanks for your interest in improving this project! Bug reports, ideas and pull
requests are welcome - open an issue or a pull request on
https://github.com/sideeffects69.

## Before you open a pull request

- [ ] Run the tests (`run_tests.bat` on Windows, `./run_tests.sh` elsewhere) and make sure they pass.
- [ ] Keep functions small, named in `snake_case`, with a short docstring and type hints.
- [ ] New settings go in the right `/config/*.py` file with a plain-language explanation and example values, are validated in `/modules/validator.py`, and (if users should edit them) are listed in `config_schema.py`.
- [ ] **Never commit personal data.** The `/config/*.py` files are generic templates; real values belong in the private data folder the control panel writes to (see the README).
- [ ] My contribution is my own work, or I have the right to submit it.

## Licensing of contributions

This project is licensed under the **MIT License** (see [`LICENSE`](LICENSE)). By
opening a pull request, you agree that your contribution is your own work (or that
you have the right to submit it) and that it is provided under the MIT License.
