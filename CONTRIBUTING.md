# Contributing to Lunar Tools Project

We welcome contributions to the Lunar Tools Project! By participating, you agree to abide by our Code of Conduct.

## How to Contribute

1.  **Fork the Repository:** Start by forking the `lunar_tools` repository to your GitHub account.

2.  **Clone Your Fork:** Clone your forked repository to your local machine:
    ```bash
    git clone https://github.com/your-username/lunar_tools.git
    cd lunar_tools
    ```

3.  **Create a Virtual Environment:** It's highly recommended to work within a virtual environment:
    ```bash
    python3 -m venv env
    source env/bin/activate  # On Windows, use `env\Scripts\activate`
    ```

4.  **Install Dependencies:** Install the project dependencies:
    ```bash
    pip install -r requirements.txt
    pip install .
    ```

5.  **Create a New Branch:** Create a new branch for your feature or bug fix:
    ```bash
    git checkout -b feature/your-feature-name
    # or
    git checkout -b bugfix/your-bug-fix-name
    ```

6.  **Make Your Changes:** Implement your changes, adhering to the existing code style and conventions.

7.  **Run Tests:** Before committing, ensure all tests pass and add new tests for your changes if applicable:
    ```bash
    pytest
    ```

8.  **Run Linters and Type Checks:** Ensure your code adheres to our quality standards:
    ```bash
    ruff check .
    mypy lunar_tools_art.py prototypes/
    ```

9.  **Commit Your Changes:** Write clear and concise commit messages:
    ```bash
    git commit -m "feat: Add new amazing feature"
    # or
    git commit -m "fix: Resolve critical bug"
    ```

10. **Push to Your Fork:** Push your changes to your forked repository:
    ```bash
    git push origin feature/your-feature-name
    ```

11. **Create a Pull Request:** Open a pull request from your forked repository to the `main` branch of the original `lunar_tools` repository. Please fill out the pull request template thoroughly.

## Reporting Bugs

If you encounter a bug, please open an issue using the "Bug Report" template. Provide as much detail as possible, including steps to reproduce, expected behavior, and actual behavior.

## Suggesting Enhancements

For new features or improvements, please open an issue using the "Feature Request" template. Describe your idea and its potential benefits.

## Code Style

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code. We use `ruff` for linting and `mypy` for type checking. Please ensure your code passes these checks before submitting a pull request.

## Questions?

If you have any questions, feel free to open an issue or reach out to the maintainers.
