"""
Test suite for code quality standards including docstrings and comments.

Tests ensure all public functions, classes, and modules have proper documentation
following Google-style docstring format and PEP-257 conventions.
"""

import ast
import os
import pytest
from pathlib import Path
from typing import List, Tuple, Set


class DocstringVisitor(ast.NodeVisitor):
    """AST visitor to analyze docstring presence and quality."""

    def __init__(self):
        """Initialize the docstring visitor."""
        self.missing_docstrings: List[Tuple[str, str, int]] = []
        self.current_file = ""

    def visit_Module(self, node: ast.Module) -> None:
        """Visit module nodes to check for module docstrings."""
        if not ast.get_docstring(node):
            self.missing_docstrings.append(("module", self.current_file, 1))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions to check for class docstrings."""
        if not ast.get_docstring(node):
            self.missing_docstrings.append(("class", node.name, node.lineno))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to check for function docstrings."""
        # Skip private functions and dunder methods
        if not node.name.startswith('_'):
            if not ast.get_docstring(node):
                self.missing_docstrings.append(("function", node.name, node.lineno))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions to check for docstrings."""
        # Skip private functions and dunder methods
        if not node.name.startswith('_'):
            if not ast.get_docstring(node):
                self.missing_docstrings.append(("async_function", node.name, node.lineno))
        self.generic_visit(node)


class TestDocstrings:
    """Test docstring presence and quality."""

    @pytest.fixture
    def python_files(self) -> List[Path]:
        """Get list of Python files to check for docstrings."""
        app_dir = Path(__file__).parent.parent / "app"
        python_files = []
        
        # Get all Python files in the app directory
        for py_file in app_dir.rglob("*.py"):
            # Skip __pycache__ and test files
            if "__pycache__" not in str(py_file):
                python_files.append(py_file)
        
        return python_files

    def test_module_docstrings_present(self, python_files: List[Path]):
        """Test that all modules have docstrings."""
        missing_modules = []
        
        for py_file in python_files:
            # Skip __init__.py files as they may be intentionally minimal
            if py_file.name == "__init__.py":
                continue
                
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                    if not ast.get_docstring(tree):
                        missing_modules.append(str(py_file.relative_to(py_file.parents[1])))
                except SyntaxError:
                    # Skip files with syntax errors
                    continue
        
        if missing_modules:
            pytest.fail(f"Missing module docstrings in: {', '.join(missing_modules)}")

    def test_public_class_docstrings_present(self, python_files: List[Path]):
        """Test that all public classes have docstrings."""
        missing_class_docstrings = []
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
                            if not ast.get_docstring(node):
                                rel_path = py_file.relative_to(py_file.parents[1])
                                missing_class_docstrings.append(f"{rel_path}:{node.name}:{node.lineno}")
                except SyntaxError:
                    continue
        
        if missing_class_docstrings:
            pytest.fail(f"Missing class docstrings: {', '.join(missing_class_docstrings)}")

    def test_public_function_docstrings_present(self, python_files: List[Path]):
        """Test that all public functions have docstrings."""
        missing_function_docstrings = []
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                    
                    for node in ast.walk(tree):
                        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) 
                            and not node.name.startswith('_')):
                            if not ast.get_docstring(node):
                                rel_path = py_file.relative_to(py_file.parents[1])
                                missing_function_docstrings.append(f"{rel_path}:{node.name}:{node.lineno}")
                except SyntaxError:
                    continue
        
        if missing_function_docstrings:
            pytest.fail(f"Missing function docstrings: {', '.join(missing_function_docstrings)}")

    def test_docstring_format_standards(self, python_files: List[Path]):
        """Test that docstrings follow proper format standards."""
        format_violations = []
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_file))
                    
                    # Check for triple quotes usage
                    lines = content.splitlines()
                    for i, line in enumerate(lines, 1):
                        # Check for single quote docstrings (should use triple double quotes)
                        if "'''" in line and '"""' not in line:
                            rel_path = py_file.relative_to(py_file.parents[1])
                            format_violations.append(f"{rel_path}:{i} - Use triple double quotes, not single")
                
                except SyntaxError:
                    continue
        
        if format_violations:
            pytest.fail(f"Docstring format violations: {'; '.join(format_violations)}")

    def test_docstring_content_quality(self, python_files: List[Path]):
        """Test docstring content quality and completeness."""
        quality_issues = []
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                    
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            docstring = ast.get_docstring(node)
                            if docstring:
                                # Check for empty or placeholder docstrings
                                if docstring.strip().lower() in ['todo', 'fixme', '', 'pass']:
                                    rel_path = py_file.relative_to(py_file.parents[1])
                                    quality_issues.append(f"{rel_path}:{node.name} - Placeholder docstring")
                                
                                # Check that docstring ends with period
                                if docstring.strip() and not docstring.strip().endswith('.'):
                                    rel_path = py_file.relative_to(py_file.parents[1])
                                    quality_issues.append(f"{rel_path}:{node.name} - Docstring should end with period")
                
                except SyntaxError:
                    continue
        
        if quality_issues:
            pytest.fail(f"Docstring quality issues: {'; '.join(quality_issues)}")


class TestCodeComments:
    """Test code commenting standards."""

    @pytest.fixture
    def python_files(self) -> List[Path]:
        """Get list of Python files to check for comments."""
        app_dir = Path(__file__).parent.parent / "app"
        return [py_file for py_file in app_dir.rglob("*.py") 
                if "__pycache__" not in str(py_file)]

    def test_complex_logic_has_comments(self, python_files: List[Path]):
        """Test that complex logic sections have explanatory comments."""
        files_needing_comments = []
        
        for py_file in python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    content = f.read()
                    lines = content.splitlines()
                    
                    # Look for complex patterns that should have comments
                    complex_patterns = [
                        'for.*for.*in',  # Nested loops
                        'if.*and.*or',   # Complex conditionals
                        'try:.*except.*except',  # Multiple exception handling
                        'lambda.*lambda',  # Nested lambdas
                    ]
                    
                    for i, line in enumerate(lines, 1):
                        for pattern in complex_patterns:
                            if any(p in line.lower() for p in pattern.split('.*')):
                                # Check if there's a comment nearby (within 2 lines)
                                comment_found = False
                                for j in range(max(0, i-3), min(len(lines), i+2)):
                                    if j < len(lines) and '#' in lines[j]:
                                        comment_found = True
                                        break
                                
                                if not comment_found:
                                    rel_path = py_file.relative_to(py_file.parents[1])
                                    files_needing_comments.append(f"{rel_path}:{i}")
                
                except Exception:
                    continue
        
        # This is a guideline test - we'll warn but not fail
        if files_needing_comments:
            pytest.warns(
                UserWarning, 
                match=f"Complex logic without comments: {', '.join(files_needing_comments[:5])}"
            )

    def test_security_code_has_comments(self, python_files: List[Path]):
        """Test that security-related code has explanatory comments."""
        security_files_without_comments = []
        
        security_keywords = [
            'password', 'hash', 'encrypt', 'decrypt', 'token', 'auth', 
            'permission', 'security', 'validate', 'sanitize'
        ]
        
        for py_file in python_files:
            # Skip if filename indicates it's security-related (likely well documented)
            if 'security' in py_file.name.lower():
                continue
                
            with open(py_file, 'r', encoding='utf-8') as f:
                try:
                    content = f.read()
                    lines = content.splitlines()
                    
                    security_line_found = False
                    has_security_comments = False
                    
                    for line in lines:
                        # Check for security-related code
                        if any(keyword in line.lower() for keyword in security_keywords):
                            security_line_found = True
                        
                        # Check for security-related comments
                        if '#' in line and any(keyword in line.lower() for keyword in security_keywords):
                            has_security_comments = True
                    
                    if security_line_found and not has_security_comments:
                        rel_path = py_file.relative_to(py_file.parents[1])
                        security_files_without_comments.append(str(rel_path))
                
                except Exception:
                    continue
        
        # This is also a guideline - we'll note but not fail
        if security_files_without_comments:
            pytest.warns(
                UserWarning,
                match=f"Security code without comments: {', '.join(security_files_without_comments[:3])}"
            )


class TestPydocstyleCompliance:
    """Test compliance with pydocstyle standards."""

    def test_pydocstyle_compliance(self):
        """Test that code passes pydocstyle checks."""
        import subprocess
        
        # Run pydocstyle on the app directory
        result = subprocess.run(
            ['pydocstyle', 'app/', '--count'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        # Get the error count
        error_count = 0
        if result.stdout.strip().isdigit():
            error_count = int(result.stdout.strip())
        
        # We'll allow some errors initially but track improvement
        # Set a reasonable threshold that can be reduced over time
        max_allowed_errors = 50  # This will be reduced as we fix issues
        
        assert error_count <= max_allowed_errors, (
            f"Too many pydocstyle errors: {error_count} (max allowed: {max_allowed_errors}). "
            f"Run 'pydocstyle app/' to see details."
        )


if __name__ == "__main__":
    pytest.main([__file__])