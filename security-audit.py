#!/usr/bin/env python3
"""
Comprehensive security audit script for FastAPI Celery application.

Performs dependency auditing, configuration validation, and security analysis.
"""

import os
import sys
import json
import subprocess
import hashlib
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SecurityIssue:
    """Represents a security issue found during audit."""
    severity: str  # critical, high, medium, low
    category: str  # dependency, config, code, etc.
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    cve_id: Optional[str] = None
    recommendation: Optional[str] = None


class SecurityAuditor:
    """Comprehensive security auditing tool."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.issues: List[SecurityIssue] = []
        self.report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "total_issues": 0,
            "critical_issues": 0,
            "high_issues": 0,
            "medium_issues": 0,
            "low_issues": 0,
            "categories": {},
            "issues": []
        }
    
    def add_issue(self, issue: SecurityIssue):
        """Add a security issue to the report."""
        self.issues.append(issue)
        self.report_data["issues"].append({
            "severity": issue.severity,
            "category": issue.category,
            "title": issue.title,
            "description": issue.description,
            "file_path": issue.file_path,
            "line_number": issue.line_number,
            "cve_id": issue.cve_id,
            "recommendation": issue.recommendation
        })
        
        # Update counters
        self.report_data["total_issues"] += 1
        self.report_data[f"{issue.severity}_issues"] += 1
        
        if issue.category not in self.report_data["categories"]:
            self.report_data["categories"][issue.category] = 0
        self.report_data["categories"][issue.category] += 1
    
    def audit_dependencies(self) -> bool:
        """Audit Python dependencies for known vulnerabilities."""
        print("🔍 Auditing Python dependencies...")
        
        requirements_files = [
            "docker/backend/requirements.txt",
            "docker/celeryworker/requirements.txt",
            "docker/tests/requirements.txt"
        ]
        
        has_vulnerabilities = False
        
        for req_file in requirements_files:
            req_path = self.project_root / req_file
            if not req_path.exists():
                continue
            
            print(f"  📄 Checking {req_file}...")
            
            # Run Safety check
            if self._check_safety_available():
                safety_issues = self._run_safety_check(req_path)
                has_vulnerabilities = has_vulnerabilities or len(safety_issues) > 0
            
            # Check for pinned versions
            self._check_pinned_versions(req_path)
            
            # Check for deprecated packages
            self._check_deprecated_packages(req_path)
            
            # Check for malicious packages
            self._check_malicious_patterns(req_path)
        
        return has_vulnerabilities
    
    def audit_configurations(self) -> bool:
        """Audit configuration files for security issues."""
        print("🔍 Auditing configuration files...")
        
        config_files = [
            "docker-compose.yml",
            "docker-compose-hardened.yml",
            "docker-compose-dev.yml",
            ".env.hardened.example",
            "backend/app/config.py",
            "docker/nginx/nginx.conf",
            "docker/nginx/nginx-hardened.conf",
            "docker/redis/redis.conf", 
            "docker/redis/redis-hardened.conf"
        ]
        
        has_issues = False
        
        for config_file in config_files:
            config_path = self.project_root / config_file
            if not config_path.exists():
                continue
            
            print(f"  📄 Checking {config_file}...")
            
            # Check for hardcoded secrets
            secrets_found = self._check_hardcoded_secrets(config_path)
            has_issues = has_issues or secrets_found
            
            # Check for insecure configurations
            insecure_configs = self._check_insecure_configs(config_path)
            has_issues = has_issues or insecure_configs
            
            # Check file permissions
            self._check_file_permissions(config_path)
        
        return has_issues
    
    def audit_source_code(self) -> bool:
        """Audit source code for security vulnerabilities."""
        print("🔍 Auditing source code...")
        
        has_issues = False
        
        # Run Bandit static analysis
        if self._check_bandit_available():
            bandit_issues = self._run_bandit_scan()
            has_issues = has_issues or len(bandit_issues) > 0
        
        # Check for SQL injection vulnerabilities
        sql_issues = self._check_sql_injection()
        has_issues = has_issues or len(sql_issues) > 0
        
        # Check for XSS vulnerabilities
        xss_issues = self._check_xss_vulnerabilities()
        has_issues = has_issues or len(xss_issues) > 0
        
        # Check for insecure cryptography
        crypto_issues = self._check_cryptography_usage()
        has_issues = has_issues or len(crypto_issues) > 0
        
        # Check for authentication issues
        auth_issues = self._check_authentication_security()
        has_issues = has_issues or len(auth_issues) > 0
        
        return has_issues
    
    def audit_docker_security(self) -> bool:
        """Audit Docker configurations for security issues."""
        print("🔍 Auditing Docker security...")
        
        has_issues = False
        
        # Check Dockerfile security
        dockerfiles = [
            "docker/backend/Dockerfile",
            "docker/backend/Dockerfile.hardened",
            "docker/celeryworker/Dockerfile",
            "docker/celeryworker/Dockerfile.hardened",
            "docker/redis/Dockerfile.hardened",
            "docker/nginx/Dockerfile.hardened"
        ]
        
        for dockerfile in dockerfiles:
            dockerfile_path = self.project_root / dockerfile
            if dockerfile_path.exists():
                print(f"  🐳 Checking {dockerfile}...")
                dockerfile_issues = self._audit_dockerfile(dockerfile_path)
                has_issues = has_issues or len(dockerfile_issues) > 0
        
        # Check Docker Compose security
        compose_files = [
            "docker-compose.yml",
            "docker-compose-hardened.yml",
            "docker-compose-dev.yml"
        ]
        
        for compose_file in compose_files:
            compose_path = self.project_root / compose_file
            if compose_path.exists():
                print(f"  🐳 Checking {compose_file}...")
                compose_issues = self._audit_docker_compose(compose_path)
                has_issues = has_issues or len(compose_issues) > 0
        
        return has_issues
    
    def audit_secrets_management(self) -> bool:
        """Audit secrets management practices."""
        print("🔍 Auditing secrets management...")
        
        has_issues = False
        
        # Check for exposed secrets in files
        secret_files = self._find_potential_secret_files()
        for secret_file in secret_files:
            print(f"  🔐 Checking {secret_file}...")
            if self._scan_file_for_secrets(secret_file):
                has_issues = True
        
        # Check environment variable security
        env_issues = self._check_environment_security()
        has_issues = has_issues or len(env_issues) > 0
        
        # Check for weak randomness
        randomness_issues = self._check_randomness_usage()
        has_issues = has_issues or len(randomness_issues) > 0
        
        return has_issues
    
    def generate_report(self, output_file: str = "security-audit-report.json"):
        """Generate comprehensive security audit report."""
        
        # Update final statistics
        self.report_data["summary"] = {
            "total_files_scanned": len(set(
                issue.file_path for issue in self.issues 
                if issue.file_path
            )),
            "critical_count": self.report_data["critical_issues"],
            "high_count": self.report_data["high_issues"],
            "medium_count": self.report_data["medium_issues"],
            "low_count": self.report_data["low_issues"],
            "categories": self.report_data["categories"]
        }
        
        # Write JSON report
        with open(output_file, 'w') as f:
            json.dump(self.report_data, f, indent=2)
        
        # Generate markdown report
        md_file = output_file.replace('.json', '.md')
        self._generate_markdown_report(md_file)
        
        print(f"\n📊 Security audit completed!")
        print(f"   📄 JSON report: {output_file}")
        print(f"   📄 Markdown report: {md_file}")
        print(f"   🚨 Total issues: {self.report_data['total_issues']}")
        print(f"   🔥 Critical: {self.report_data['critical_issues']}")
        print(f"   ⚠️  High: {self.report_data['high_issues']}")
        print(f"   ⚡ Medium: {self.report_data['medium_issues']}")
        print(f"   ℹ️  Low: {self.report_data['low_issues']}")
    
    def _check_safety_available(self) -> bool:
        """Check if Safety tool is available."""
        try:
            subprocess.run(['safety', '--version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  ⚠️ Safety tool not available, skipping vulnerability check")
            return False
    
    def _run_safety_check(self, requirements_file: Path) -> List[SecurityIssue]:
        """Run Safety vulnerability check on requirements file."""
        issues = []
        
        try:
            result = subprocess.run([
                'safety', 'check', '-r', str(requirements_file), '--json'
            ], capture_output=True, text=True)
            
            if result.returncode != 0 and result.stdout:
                try:
                    vulnerabilities = json.loads(result.stdout)
                    for vuln in vulnerabilities:
                        issues.append(SecurityIssue(
                            severity="high",
                            category="dependency",
                            title=f"Vulnerable package: {vuln.get('package')}",
                            description=f"CVE: {vuln.get('vulnerability_id')} - {vuln.get('advisory')}",
                            file_path=str(requirements_file),
                            cve_id=vuln.get('vulnerability_id'),
                            recommendation=f"Update {vuln.get('package')} to version {vuln.get('safe_versions', 'latest')}"
                        ))
                        self.add_issue(issues[-1])
                except json.JSONDecodeError:
                    pass
                    
        except subprocess.CalledProcessError:
            pass
        
        return issues
    
    def _check_pinned_versions(self, requirements_file: Path):
        """Check for unpinned dependency versions."""
        with open(requirements_file, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if line and not line.startswith('#'):
                # Check for unpinned versions
                if '==' not in line and '>=' not in line and '~=' not in line:
                    if not line.startswith('-') and '://' not in line:
                        self.add_issue(SecurityIssue(
                            severity="medium",
                            category="dependency",
                            title="Unpinned dependency version",
                            description=f"Dependency '{line}' should have a pinned version for security",
                            file_path=str(requirements_file),
                            line_number=i,
                            recommendation="Pin dependency to specific version (e.g., package==1.2.3)"
                        ))
    
    def _check_deprecated_packages(self, requirements_file: Path):
        """Check for deprecated or unmaintained packages."""
        deprecated_packages = {
            'django': 'Check for deprecated Django versions < 3.2',
            'flask': 'Check for deprecated Flask versions < 1.1',
            'requests': 'Check for deprecated requests versions < 2.25',
            'urllib3': 'Check for deprecated urllib3 versions < 1.26',
            'pillow': 'Check for deprecated Pillow versions < 8.0',
            'pycrypto': 'Replace with pycryptodome',
            'python-jwt': 'Replace with pyjwt'
        }
        
        with open(requirements_file, 'r') as f:
            content = f.read()
        
        for package, warning in deprecated_packages.items():
            if package in content.lower():
                self.add_issue(SecurityIssue(
                    severity="medium",
                    category="dependency",
                    title=f"Potentially deprecated package: {package}",
                    description=warning,
                    file_path=str(requirements_file),
                    recommendation="Review package status and consider alternatives"
                ))
    
    def _check_malicious_patterns(self, requirements_file: Path):
        """Check for suspicious package patterns."""
        suspicious_patterns = [
            r'git\+https?://.*\.git',  # Git dependencies
            r'file:///',               # Local file dependencies
        ]
        
        # Only check for test packages in production requirements, not test requirements
        if 'test' not in str(requirements_file).lower():
            suspicious_patterns.append(r'[a-zA-Z0-9\-_]*(?:test|fake|mock)[a-zA-Z0-9\-_]*==')  # Test packages in production
        
        with open(requirements_file, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in suspicious_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip legitimate testing packages in test requirements
                    if ('test' in str(requirements_file).lower() and 
                        any(test_pkg in line.lower() for test_pkg in ['pytest', 'allure', 'fakeredis'])):
                        continue
                    
                    self.add_issue(SecurityIssue(
                        severity="medium",
                        category="dependency",
                        title="Suspicious dependency pattern",
                        description=f"Line contains suspicious pattern: {line.strip()}",
                        file_path=str(requirements_file),
                        line_number=i,
                        recommendation="Review dependency source and necessity"
                    ))
    
    def _check_hardcoded_secrets(self, file_path: Path) -> bool:
        """Check file for hardcoded secrets."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return False
        
        # Secret patterns
        secret_patterns = [
            (r'password\s*[:=]\s*["\'][^"\']{8,}["\']', "hardcoded password"),
            (r'secret\s*[:=]\s*["\'][^"\']{16,}["\']', "hardcoded secret"),
            (r'token\s*[:=]\s*["\'][^"\']{20,}["\']', "hardcoded token"),
            (r'api_key\s*[:=]\s*["\'][^"\']{16,}["\']', "hardcoded API key"),
            (r'private_key\s*[:=]\s*["\'][^"\']{32,}["\']', "hardcoded private key"),
            (r'[A-Za-z0-9+/]{40,}={0,2}', "potential base64 encoded secret"),
            (r'sk_[a-zA-Z0-9]{24,}', "Stripe secret key"),
            (r'AKIA[0-9A-Z]{16}', "AWS access key"),
            (r'ghp_[a-zA-Z0-9]{36}', "GitHub personal access token"),
        ]
        
        found_secrets = False
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Skip comments, obvious examples, and print statements
            if (line.strip().startswith('#') or 
                'example' in line.lower() or 
                'test' in line.lower() or
                'print(' in line.lower() or
                'echo' in line.lower() or
                'logger' in line.lower() or
                'log(' in line.lower() or
                'f"' in line or "f'" in line):
                continue
            
            for pattern, description in secret_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                if matches:
                    # Filter out obvious false positives
                    for match in matches:
                        if not any(fp in match.lower() for fp in ['example', 'test', 'dummy', 'placeholder', 'xxx', 'hashed', '{hashed}', 'changeme', 'your_', 'set_']):
                            # Additional context check for environment variable examples
                            if "ADMIN_PASSWORD='" not in line and "PASSWORD='" not in line:
                                self.add_issue(SecurityIssue(
                                    severity="critical",
                                    category="secrets",
                                    title=f"Potential {description}",
                                    description=f"Found potential secret in file: {match[:20]}...",
                                    file_path=str(file_path),
                                    line_number=i,
                                    recommendation="Remove hardcoded secret and use environment variables"
                                ))
                                found_secrets = True
        
        return found_secrets
    
    def _check_insecure_configs(self, file_path: Path) -> bool:
        """Check for insecure configuration patterns."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return False
        
        insecure_patterns = [
            (r'debug\s*[:=]\s*true', "Debug mode enabled", "medium"),
            (r'ssl_verify\s*[:=]\s*false', "SSL verification disabled", "high"),
            (r'verify\s*[:=]\s*false', "Verification disabled", "medium"),
            (r'host\s*[:=]\s*["\']0\.0\.0\.0["\']', "Bind to all interfaces", "medium"),
            (r'privileged\s*:\s*true', "Privileged container", "high"),
            (r'cap_add\s*:.*SYS_ADMIN', "Dangerous capability", "high"),
            (r'security_opt\s*:.*apparmor:unconfined', "AppArmor disabled", "medium"),
            (r'--insecure', "Insecure flag used", "medium"),
        ]
        
        found_issues = False
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            for pattern, description, severity in insecure_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self.add_issue(SecurityIssue(
                        severity=severity,
                        category="configuration",
                        title=f"Insecure configuration: {description}",
                        description=f"Found insecure configuration pattern in line: {line.strip()}",
                        file_path=str(file_path),
                        line_number=i,
                        recommendation="Review and secure configuration setting"
                    ))
                    found_issues = True
        
        return found_issues
    
    def _check_file_permissions(self, file_path: Path):
        """Check file permissions for security issues."""
        try:
            stat = file_path.stat()
            mode = stat.st_mode
            
            # Check if file is world-writable
            if mode & 0o002:
                self.add_issue(SecurityIssue(
                    severity="medium",
                    category="permissions",
                    title="World-writable file",
                    description=f"File {file_path} is writable by others",
                    file_path=str(file_path),
                    recommendation="Remove world-write permissions (chmod o-w)"
                ))
            
            # Check if config file is world-readable
            if 'config' in str(file_path).lower() and mode & 0o004:
                self.add_issue(SecurityIssue(
                    severity="low",
                    category="permissions",
                    title="World-readable config file",
                    description=f"Configuration file {file_path} is readable by others",
                    file_path=str(file_path),
                    recommendation="Restrict read permissions for config files"
                ))
                
        except Exception:
            pass
    
    def _check_bandit_available(self) -> bool:
        """Check if Bandit tool is available."""
        try:
            subprocess.run(['bandit', '--version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  ⚠️ Bandit tool not available, skipping static analysis")
            return False
    
    def _run_bandit_scan(self) -> List[SecurityIssue]:
        """Run Bandit static analysis."""
        issues = []
        backend_dir = self.project_root / "backend"
        
        if not backend_dir.exists():
            return issues
        
        try:
            result = subprocess.run([
                'bandit', '-r', str(backend_dir), '-f', 'json'
            ], capture_output=True, text=True)
            
            if result.stdout:
                try:
                    bandit_data = json.loads(result.stdout)
                    for result_item in bandit_data.get('results', []):
                        severity_map = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
                        severity = severity_map.get(result_item.get('issue_severity', 'MEDIUM'), 'medium')
                        
                        issue = SecurityIssue(
                            severity=severity,
                            category="code",
                            title=f"Static analysis: {result_item.get('test_name')}",
                            description=result_item.get('issue_text', ''),
                            file_path=result_item.get('filename'),
                            line_number=result_item.get('line_number'),
                            recommendation=result_item.get('more_info', 'Review code for security issues')
                        )
                        issues.append(issue)
                        self.add_issue(issue)
                        
                except json.JSONDecodeError:
                    pass
                    
        except subprocess.CalledProcessError:
            pass
        
        return issues
    
    def _find_potential_secret_files(self) -> List[Path]:
        """Find files that might contain secrets."""
        secret_file_patterns = [
            "**/.env*",
            "**/config.*",
            "**/*secret*",
            "**/*password*", 
            "**/*key*",
            "**/*.pem",
            "**/*.key",
            "**/*.p12",
            "**/*.pfx"
        ]
        
        secret_files = []
        for pattern in secret_file_patterns:
            secret_files.extend(self.project_root.glob(pattern))
        
        # Filter out obvious non-secret files and directories to skip
        skip_patterns = [
            'test', 'example', 'sample', '.git', '.venv', 'venv', 'env',
            'node_modules', '__pycache__', '.mypy_cache', '.pytest_cache',
            'site-packages', 'dist', 'build', '.egg-info'
        ]
        
        filtered_files = []
        for file_path in secret_files:
            if file_path.is_file():
                # Skip if any part of the path contains skip patterns
                path_str = str(file_path).lower()
                if not any(skip in path_str for skip in skip_patterns):
                    filtered_files.append(file_path)
        
        return filtered_files
    
    def _scan_file_for_secrets(self, file_path: Path) -> bool:
        """Scan a specific file for secrets."""
        return self._check_hardcoded_secrets(file_path)
    
    def _check_environment_security(self) -> List[SecurityIssue]:
        """Check environment variable security."""
        issues = []
        
        # Check for common insecure environment variable patterns
        env_files = list(self.project_root.glob("**/.env*"))
        
        for env_file in env_files:
            if env_file.is_file():
                issues.extend(self._audit_env_file(env_file))
        
        return issues
    
    def _audit_env_file(self, env_file: Path) -> List[SecurityIssue]:
        """Audit a specific environment file."""
        issues = []
        
        try:
            with open(env_file, 'r') as f:
                content = f.read()
        except Exception:
            return issues
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                
                # Check for weak passwords
                if 'password' in key.lower() and value:
                    if len(value) < 12:
                        issues.append(SecurityIssue(
                            severity="medium",
                            category="secrets",
                            title="Weak password in environment",
                            description=f"Password '{key}' appears to be weak (< 12 characters)",
                            file_path=str(env_file),
                            line_number=i,
                            recommendation="Use strong passwords (12+ characters, mixed case, numbers, symbols)"
                        ))
                        self.add_issue(issues[-1])
                
                # Check for default values
                if value.lower() in ['password', 'secret', 'changeme', 'admin', '123456']:
                    issues.append(SecurityIssue(
                        severity="high",
                        category="secrets",
                        title="Default/weak secret value",
                        description=f"Environment variable '{key}' has a default/weak value",
                        file_path=str(env_file),
                        line_number=i,
                        recommendation="Change to a strong, unique value"
                    ))
                    self.add_issue(issues[-1])
        
        return issues
    
    def _get_project_python_files(self) -> List[Path]:
        """Get Python files from project, excluding virtual environments and cache directories."""
        python_files = list(self.project_root.glob("**/*.py"))
        
        skip_patterns = [
            '.venv', 'venv', 'env', '__pycache__', '.mypy_cache', '.pytest_cache',
            'site-packages', 'dist', 'build', '.egg-info', 'node_modules'
        ]
        
        filtered_files = []
        for py_file in python_files:
            path_str = str(py_file).lower()
            if not any(skip in path_str for skip in skip_patterns):
                filtered_files.append(py_file)
        
        return filtered_files
    
    def _check_randomness_usage(self) -> List[SecurityIssue]:
        """Check for weak randomness usage."""
        issues = []
        
        python_files = self._get_project_python_files()
        
        for py_file in python_files:
            if py_file.is_file():
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Check for weak random usage (skip security audit script)
                        if ('random.random()' in line or 'random.randint(' in line) and 'security-audit.py' not in str(py_file):
                            if 'secrets.' not in line and 'os.urandom' not in line:
                                issue = SecurityIssue(
                                    severity="medium",
                                    category="cryptography",
                                    title="Weak randomness for security",
                                    description="Using weak random instead of cryptographically secure random",
                                    file_path=str(py_file),
                                    line_number=i,
                                    recommendation="Use secrets module or os.urandom() for security-related randomness"
                                )
                                issues.append(issue)
                                self.add_issue(issue)
                        
                        # Check for weak hash algorithms
                        weak_hashes = ['md5', 'sha1']
                        for weak_hash in weak_hashes:
                            if f'{weak_hash}(' in line.lower() or f'hashlib.{weak_hash}' in line.lower():
                                issue = SecurityIssue(
                                    severity="medium",
                                    category="cryptography",
                                    title=f"Weak hash algorithm: {weak_hash.upper()}",
                                    description=f"Using weak hash algorithm {weak_hash.upper()}",
                                    file_path=str(py_file),
                                    line_number=i,
                                    recommendation="Use SHA-256 or stronger hash algorithms"
                                )
                                issues.append(issue)
                                self.add_issue(issue)
                
                except Exception:
                    continue
        
        return issues
    
    def _check_sql_injection(self) -> List[SecurityIssue]:
        """Check for potential SQL injection vulnerabilities."""
        issues = []
        
        python_files = self._get_project_python_files()
        
        for py_file in python_files:
            if py_file.is_file():
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Check for string formatting in SQL
                        if any(sql_keyword in line.lower() for sql_keyword in ['select', 'insert', 'update', 'delete']):
                            if any(format_pattern in line for format_pattern in ['%s', '.format(', 'f"', "f'"]):
                                if 'execute(' in line or 'query(' in line:
                                    issue = SecurityIssue(
                                        severity="high",
                                        category="sql_injection",
                                        title="Potential SQL injection vulnerability",
                                        description="SQL query with string formatting detected",
                                        file_path=str(py_file),
                                        line_number=i,
                                        recommendation="Use parameterized queries or ORM methods"
                                    )
                                    issues.append(issue)
                                    self.add_issue(issue)
                
                except Exception:
                    continue
        
        return issues
    
    def _check_xss_vulnerabilities(self) -> List[SecurityIssue]:
        """Check for potential XSS vulnerabilities."""
        issues = []
        
        python_files = self._get_project_python_files()
        
        for py_file in python_files:
            if py_file.is_file():
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Check for unescaped output
                        if 'render_template_string(' in line and 'escape(' not in line:
                            issue = SecurityIssue(
                                severity="medium",
                                category="xss",
                                title="Potential XSS vulnerability",
                                description="Unescaped template string rendering",
                                file_path=str(py_file),
                                line_number=i,
                                recommendation="Escape user input or use safe template rendering"
                            )
                            issues.append(issue)
                            self.add_issue(issue)
                
                except Exception:
                    continue
        
        return issues
    
    def _check_cryptography_usage(self) -> List[SecurityIssue]:
        """Check for insecure cryptography usage."""
        issues = []
        
        python_files = self._get_project_python_files()
        
        for py_file in python_files:
            if py_file.is_file():
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Check for weak encryption (skip security audit script)
                        if ('DES(' in line or 'RC4(' in line) and 'security-audit.py' not in str(py_file):
                            issue = SecurityIssue(
                                severity="high",
                                category="cryptography",
                                title="Weak encryption algorithm",
                                description="Using deprecated/weak encryption algorithm",
                                file_path=str(py_file),
                                line_number=i,
                                recommendation="Use AES or other modern encryption algorithms"
                            )
                            issues.append(issue)
                            self.add_issue(issue)
                        
                        # Check for hardcoded keys (skip security audit script itself)
                        if ('key=' in line and ('b"' in line or "b'" in line) and 
                            'security-audit.py' not in str(py_file) and
                            'test' not in str(py_file).lower() and
                            'example' not in line.lower()):
                            if len(line) > 40:  # Likely a hardcoded key
                                issue = SecurityIssue(
                                    severity="critical",
                                    category="cryptography",
                                    title="Hardcoded encryption key",
                                    description="Encryption key appears to be hardcoded",
                                    file_path=str(py_file),
                                    line_number=i,
                                    recommendation="Load keys from secure environment variables or key management"
                                )
                                issues.append(issue)
                                self.add_issue(issue)
                
                except Exception:
                    continue
        
        return issues
    
    def _check_authentication_security(self) -> List[SecurityIssue]:
        """Check authentication security implementation."""
        issues = []
        
        python_files = self._get_project_python_files()
        
        for py_file in python_files:
            if py_file.is_file():
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Check for weak password hashing (skip security audit script)
                        if (any(weak_hash in line.lower() for weak_hash in ['md5', 'sha1', 'sha256']) and 
                            'password' in line.lower() and 
                            'security-audit.py' not in str(py_file)):
                            if 'bcrypt' not in line.lower() and 'scrypt' not in line.lower() and 'pbkdf2' not in line.lower():
                                issue = SecurityIssue(
                                    severity="high",
                                    category="authentication",
                                    title="Weak password hashing",
                                    description="Using weak hash function for passwords",
                                    file_path=str(py_file),
                                    line_number=i,
                                    recommendation="Use bcrypt, scrypt, or PBKDF2 for password hashing"
                                )
                                issues.append(issue)
                                self.add_issue(issue)
                        
                        # Check for session security
                        if 'session[' in line and 'secure=' not in line:
                            issue = SecurityIssue(
                                severity="medium",
                                category="authentication",
                                title="Insecure session configuration",
                                description="Session may not be configured securely",
                                file_path=str(py_file),
                                line_number=i,
                                recommendation="Configure sessions with secure=True and httponly=True"
                            )
                            issues.append(issue)
                            self.add_issue(issue)
                
                except Exception:
                    continue
        
        return issues
    
    def _audit_dockerfile(self, dockerfile_path: Path) -> List[SecurityIssue]:
        """Audit Dockerfile for security issues."""
        issues = []
        
        try:
            with open(dockerfile_path, 'r') as f:
                content = f.read()
        except Exception:
            return issues
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            
            # Check for running as root
            if line.upper().startswith('USER') and 'root' in line.lower():
                issue = SecurityIssue(
                    severity="high",
                    category="docker",
                    title="Container running as root",
                    description="Dockerfile configures container to run as root user",
                    file_path=str(dockerfile_path),
                    line_number=i,
                    recommendation="Create and use a non-root user"
                )
                issues.append(issue)
                self.add_issue(issue)
            
            # Check for latest tag
            if line.upper().startswith('FROM') and ':latest' in line:
                issue = SecurityIssue(
                    severity="medium",
                    category="docker",
                    title="Using latest tag",
                    description="Using 'latest' tag for base image",
                    file_path=str(dockerfile_path),
                    line_number=i,
                    recommendation="Pin to specific image version"
                )
                issues.append(issue)
                self.add_issue(issue)
            
            # Check for ADD instead of COPY
            if line.upper().startswith('ADD'):
                issue = SecurityIssue(
                    severity="low",
                    category="docker",
                    title="Using ADD instead of COPY",
                    description="ADD has additional features that may pose security risks",
                    file_path=str(dockerfile_path),
                    line_number=i,
                    recommendation="Use COPY instead of ADD unless auto-extraction is needed"
                )
                issues.append(issue)
                self.add_issue(issue)
        
        return issues
    
    def _audit_docker_compose(self, compose_path: Path) -> List[SecurityIssue]:
        """Audit Docker Compose file for security issues."""
        issues = []
        
        try:
            with open(compose_path, 'r') as f:
                content = f.read()
        except Exception:
            return issues
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Check for privileged containers
            if 'privileged:' in line and 'true' in line:
                issue = SecurityIssue(
                    severity="critical",
                    category="docker",
                    title="Privileged container",
                    description="Container running in privileged mode",
                    file_path=str(compose_path),
                    line_number=i,
                    recommendation="Remove privileged mode and use specific capabilities"
                )
                issues.append(issue)
                self.add_issue(issue)
            
            # Check for host network mode
            if 'network_mode:' in line and 'host' in line:
                issue = SecurityIssue(
                    severity="high",
                    category="docker",
                    title="Host network mode",
                    description="Container using host network mode",
                    file_path=str(compose_path),
                    line_number=i,
                    recommendation="Use bridge networking with port mapping"
                )
                issues.append(issue)
                self.add_issue(issue)
            
            # Check for bind mounts to sensitive directories
            if ':/etc' in line or ':/var' in line or ':/usr' in line:
                issue = SecurityIssue(
                    severity="medium",
                    category="docker",
                    title="Bind mount to sensitive directory",
                    description="Mounting sensitive host directory",
                    file_path=str(compose_path),
                    line_number=i,
                    recommendation="Use named volumes or mount specific files only"
                )
                issues.append(issue)
                self.add_issue(issue)
        
        return issues
    
    def _generate_markdown_report(self, output_file: str):
        """Generate markdown format report."""
        md_content = f"""# Security Audit Report

**Generated:** {self.report_data['timestamp']}
**Project:** {self.report_data['project_root']}

## Summary

- **Total Issues:** {self.report_data['total_issues']}
- **Critical:** {self.report_data['critical_issues']} 🔥
- **High:** {self.report_data['high_issues']} ⚠️
- **Medium:** {self.report_data['medium_issues']} ⚡
- **Low:** {self.report_data['low_issues']} ℹ️

## Issues by Category

"""
        
        for category, count in self.report_data['categories'].items():
            md_content += f"- **{category.title()}:** {count}\n"
        
        md_content += "\n## Detailed Issues\n\n"
        
        # Group issues by severity
        for severity in ['critical', 'high', 'medium', 'low']:
            severity_issues = [issue for issue in self.issues if issue.severity == severity]
            if severity_issues:
                md_content += f"### {severity.title()} Issues\n\n"
                
                for issue in severity_issues:
                    md_content += f"#### {issue.title}\n\n"
                    md_content += f"- **Category:** {issue.category}\n"
                    md_content += f"- **Description:** {issue.description}\n"
                    
                    if issue.file_path:
                        md_content += f"- **File:** {issue.file_path}"
                        if issue.line_number:
                            md_content += f":{issue.line_number}"
                        md_content += "\n"
                    
                    if issue.cve_id:
                        md_content += f"- **CVE:** {issue.cve_id}\n"
                    
                    if issue.recommendation:
                        md_content += f"- **Recommendation:** {issue.recommendation}\n"
                    
                    md_content += "\n"
        
        md_content += """
## Recommendations

1. **Address Critical Issues First:** Focus on critical severity issues that pose immediate security risks
2. **Review Dependencies:** Regularly update dependencies and monitor for vulnerabilities
3. **Secure Configuration:** Review all configuration files for security best practices
4. **Code Review:** Implement security-focused code review processes
5. **Continuous Monitoring:** Set up automated security scanning in CI/CD pipeline

## Next Steps

1. Fix all critical and high severity issues
2. Implement automated security scanning
3. Regular dependency updates
4. Security training for development team
5. Penetration testing for production deployment
"""
        
        with open(output_file, 'w') as f:
            f.write(md_content)


def main():
    """Main entry point for security audit."""
    print("🔒 FastAPI Celery Security Audit")
    print("================================")
    
    # Initialize auditor
    auditor = SecurityAuditor()
    
    # Run comprehensive audit
    print("\n🚀 Starting comprehensive security audit...\n")
    
    # Audit different categories
    dep_issues = auditor.audit_dependencies()
    config_issues = auditor.audit_configurations() 
    code_issues = auditor.audit_source_code()
    docker_issues = auditor.audit_docker_security()
    secrets_issues = auditor.audit_secrets_management()
    
    # Generate reports
    auditor.generate_report()
    
    # Summary
    total_issues = auditor.report_data['total_issues']
    if total_issues == 0:
        print("\n✅ No security issues found!")
        return 0
    else:
        critical = auditor.report_data['critical_issues']
        high = auditor.report_data['high_issues']
        
        if critical > 0:
            print(f"\n🚨 CRITICAL: {critical} critical security issues found!")
            return 2
        elif high > 0:
            print(f"\n⚠️ WARNING: {high} high priority security issues found!")
            return 1
        else:
            print(f"\n⚡ Found {total_issues} security issues (medium/low priority)")
            return 0


if __name__ == "__main__":
    sys.exit(main())