# Security Audit Report

**Generated:** 2025-06-11T10:34:50.881851
**Project:** .

## Summary

- **Total Issues:** 10
- **Critical:** 0 🔥
- **High:** 0 ⚠️
- **Medium:** 10 ⚡
- **Low:** 0 ℹ️

## Issues by Category

- **Dependency:** 4
- **Docker:** 6

## Detailed Issues

### Medium Issues

#### Potentially deprecated package: requests

- **Category:** dependency
- **Description:** Check for deprecated requests versions < 2.25
- **File:** docker/backend/requirements.txt
- **Recommendation:** Review package status and consider alternatives

#### Potentially deprecated package: urllib3

- **Category:** dependency
- **Description:** Check for deprecated urllib3 versions < 1.26
- **File:** docker/backend/requirements.txt
- **Recommendation:** Review package status and consider alternatives

#### Potentially deprecated package: requests

- **Category:** dependency
- **Description:** Check for deprecated requests versions < 2.25
- **File:** docker/tests/requirements.txt
- **Recommendation:** Review package status and consider alternatives

#### Potentially deprecated package: urllib3

- **Category:** dependency
- **Description:** Check for deprecated urllib3 versions < 1.26
- **File:** docker/tests/requirements.txt
- **Recommendation:** Review package status and consider alternatives

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose.yml:10
- **Recommendation:** Use named volumes or mount specific files only

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose-hardened.yml:108
- **Recommendation:** Use named volumes or mount specific files only

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose-hardened.yml:110
- **Recommendation:** Use named volumes or mount specific files only

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose-hardened.yml:161
- **Recommendation:** Use named volumes or mount specific files only

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose-hardened.yml:290
- **Recommendation:** Use named volumes or mount specific files only

#### Bind mount to sensitive directory

- **Category:** docker
- **Description:** Mounting sensitive host directory
- **File:** docker-compose-hardened.yml:342
- **Recommendation:** Use named volumes or mount specific files only


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
