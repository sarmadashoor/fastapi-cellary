"""
Performance and load testing for resume processing system.

This module tests system behavior under various load conditions:
- Concurrent resume uploads (simulate 10-100+ sessions)
- Large resume files processing performance
- Rate limiter behavior under high request volume
- Memory and resource utilization patterns
"""

import asyncio
import io
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

from fastapi import status


@pytest.mark.performance
@pytest.mark.slow
class TestConcurrentUploadLoad:
    """Test system behavior under concurrent upload scenarios."""

    def test_concurrent_uploads_small_scale(self, client, admin_token):
        """Test 10 concurrent uploads to verify basic concurrency handling."""
        
        def upload_file(file_id):
            """Upload a single file and return result."""
            content = f"Resume content for user {file_id}".encode()
            
            try:
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": (f"resume_{file_id}.pdf", io.BytesIO(content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=30.0
                )
                return {
                    "file_id": file_id,
                    "status_code": response.status_code,
                    "response_data": response.json() if response.status_code in [200, 429] else None,
                    "error": None
                }
            except Exception as e:
                return {
                    "file_id": file_id,
                    "status_code": None,
                    "response_data": None,
                    "error": str(e)
                }

        # Mock Celery to avoid actual processing
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_delay.side_effect = lambda *args: MagicMock(id=f"task-{time.time()}")
            
            # Execute concurrent uploads
            num_uploads = 10
            start_time = time.time()
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(upload_file, i) for i in range(num_uploads)]
                results = [future.result() for future in as_completed(futures)]
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # Analyze results
            successful_uploads = [r for r in results if r["status_code"] == 200]
            rate_limited = [r for r in results if r["status_code"] == 429]
            errors = [r for r in results if r["error"] is not None]
            
            print(f"\nConcurrent Upload Results (10 uploads):")
            print(f"Total time: {total_time:.2f}s")
            print(f"Successful: {len(successful_uploads)}")
            print(f"Rate limited: {len(rate_limited)}")
            print(f"Errors: {len(errors)}")
            
            # Assertions
            assert len(successful_uploads) >= 1, "At least some uploads should succeed"
            assert len(errors) == 0, f"No upload errors expected, got: {errors}"
            assert total_time < 30, "All uploads should complete within 30 seconds"
            
            # Rate limiting should kick in for high concurrency
            total_processed = len(successful_uploads) + len(rate_limited)
            assert total_processed == num_uploads, "All requests should be processed"

    @pytest.mark.benchmark
    def test_upload_response_time_benchmarks(self, client, admin_token, benchmark):
        """Benchmark single upload response times."""
        
        def upload_benchmark():
            content = b"Benchmark resume content for performance testing"
            
            with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
                mock_delay.return_value = MagicMock(id="benchmark-task")
                
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("benchmark.pdf", io.BytesIO(content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                return response
        
        # Benchmark the upload operation
        result = benchmark(upload_benchmark)
        
        # Verify the benchmark result
        assert result.status_code in [200, 429], "Upload should succeed or hit rate limit"
        
        # Performance expectations (adjust based on system capabilities)
        stats = benchmark.stats
        assert stats.mean < 1.0, f"Mean response time should be under 1s, got {stats.mean:.3f}s"
        assert stats.min < 0.5, f"Minimum response time should be under 0.5s, got {stats.min:.3f}s"

    def test_rate_limiter_behavior_upload_endpoint(self, client, admin_token):
        """Test rate limiter behavior when hitting upload limits."""
        
        def rapid_upload():
            content = b"Rate limit test content"
            return client.post(
                "/api/resumes/upload",
                files={"file": ("rate_test.pdf", io.BytesIO(content), "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_delay.side_effect = lambda *args: MagicMock(id=f"rate-task-{time.time()}")
            
            responses = []
            start_time = time.time()
            
            # Make rapid requests until rate limited
            for i in range(15):  # More than the 10 req/5min limit
                response = rapid_upload()
                responses.append(response)
                
                # Stop if we hit rate limit
                if response.status_code == 429:
                    break
                    
                time.sleep(0.1)  # Small delay between requests
            
            end_time = time.time()
            
            # Analyze rate limiting behavior
            successful = [r for r in responses if r.status_code == 200]
            rate_limited = [r for r in responses if r.status_code == 429]
            
            print(f"\nRate Limiter Test Results:")
            print(f"Total requests: {len(responses)}")
            print(f"Successful: {len(successful)}")
            print(f"Rate limited: {len(rate_limited)}")
            print(f"Test duration: {end_time - start_time:.2f}s")
            
            # Verify rate limiting is working
            assert len(rate_limited) > 0, "Rate limiting should trigger"
            assert len(successful) <= 10, "Should not exceed upload rate limit"
            
            # Verify rate limit response format
            if rate_limited:
                rate_response = rate_limited[0]
                data = rate_response.json()
                assert "detail" in data
                assert "limit" in data
                assert "window" in data

    def test_status_endpoint_rate_limiter(self, client, admin_token):
        """Test rate limiter behavior for status endpoint (60 req/min)."""
        
        def rapid_status_check():
            return client.get(
                "/api/resumes/status/test-task-id",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        responses = []
        start_time = time.time()
        
        # Make rapid status requests
        for i in range(70):  # More than 60 req/min limit
            response = rapid_status_check()
            responses.append(response)
            
            if response.status_code == 429:
                break
        
        end_time = time.time()
        
        # Analyze results
        successful_or_404 = [r for r in responses if r.status_code in [200, 404]]
        rate_limited = [r for r in responses if r.status_code == 429]
        
        print(f"\nStatus Endpoint Rate Limiter Results:")
        print(f"Total requests: {len(responses)}")
        print(f"Successful/404: {len(successful_or_404)}")
        print(f"Rate limited: {len(rate_limited)}")
        print(f"Requests per second: {len(responses) / (end_time - start_time):.2f}")
        
        # Should hit rate limit eventually
        assert len(rate_limited) > 0, "Status endpoint rate limiting should trigger"


@pytest.mark.performance
@pytest.mark.slow
class TestLargeFileProcessing:
    """Test system behavior with large resume files."""

    def test_upload_max_size_boundary(self, client, admin_token):
        """Test upload performance at maximum file size (5MB)."""
        
        # Create file at exactly 5MB limit
        max_size = 5 * 1024 * 1024  # 5MB
        pdf_header = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        content = pdf_header + b"x" * (max_size - len(pdf_header))
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_delay.return_value = MagicMock(id="large-file-task")
            
            start_time = time.time()
            
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("large_resume.pdf", io.BytesIO(content), "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            end_time = time.time()
            upload_time = end_time - start_time
            
            print(f"\nLarge File Upload (5MB):")
            print(f"Upload time: {upload_time:.2f}s")
            print(f"Status: {response.status_code}")
            
            # Performance expectations
            if response.status_code == 200:
                assert upload_time < 10, f"5MB upload should complete in under 10s, took {upload_time:.2f}s"
                
                # Verify Celery was called with correct content
                mock_delay.assert_called_once()
                call_args = mock_delay.call_args[0]
                assert len(call_args[0]) == max_size, "Full content should be passed to Celery"
            elif response.status_code == 429:
                print("Hit rate limit during large file test")

    def test_memory_usage_with_large_files(self, client, admin_token):
        """Test memory behavior with multiple large file uploads."""
        
        def create_large_content(size_mb):
            size_bytes = size_mb * 1024 * 1024
            pdf_header = b"%PDF-1.4\nLarge file test\n"
            return pdf_header + b"x" * (size_bytes - len(pdf_header))
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_delay.side_effect = lambda *args: MagicMock(id=f"memory-task-{time.time()}")
            
            # Test multiple file sizes
            test_sizes = [1, 2, 3, 4]  # MB
            results = []
            
            for size_mb in test_sizes:
                content = create_large_content(size_mb)
                
                start_time = time.time()
                
                try:
                    response = client.post(
                        "/api/resumes/upload",
                        files={"file": (f"test_{size_mb}mb.pdf", io.BytesIO(content), "application/pdf")},
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    
                    end_time = time.time()
                    
                    results.append({
                        "size_mb": size_mb,
                        "upload_time": end_time - start_time,
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    })
                    
                    # Stop if we hit rate limits
                    if response.status_code == 429:
                        break
                        
                except Exception as e:
                    results.append({
                        "size_mb": size_mb,
                        "upload_time": None,
                        "status_code": None,
                        "success": False,
                        "error": str(e)
                    })
            
            print(f"\nMemory Usage Test Results:")
            for result in results:
                if result["success"]:
                    print(f"{result['size_mb']}MB: {result['upload_time']:.2f}s")
                else:
                    print(f"{result['size_mb']}MB: Failed ({result.get('error', 'HTTP error')})")
            
            # At least smaller files should succeed
            successful = [r for r in results if r["success"]]
            assert len(successful) >= 1, "At least some file sizes should upload successfully"


@pytest.mark.performance
class TestSystemResourceUtilization:
    """Test system resource usage patterns."""

    def test_concurrent_status_polling(self, client, admin_token):
        """Test system behavior under heavy status polling load."""
        
        # Mock various task states
        def mock_status_response(task_id):
            return client.get(
                f"/api/resumes/status/{task_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # Simulate multiple clients polling different tasks
        task_ids = [f"poll-task-{i}" for i in range(20)]
        
        def poll_worker(task_id):
            responses = []
            for _ in range(10):  # Each worker polls 10 times
                response = mock_status_response(task_id)
                responses.append(response.status_code)
                time.sleep(0.1)
            return responses
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(poll_worker, task_id) for task_id in task_ids[:10]]
            results = [future.result() for future in as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze polling results
        total_requests = sum(len(result) for result in results)
        successful_polls = sum(1 for result in results for status_code in result if status_code in [200, 404])
        rate_limited_polls = sum(1 for result in results for status_code in result if status_code == 429)
        
        print(f"\nConcurrent Status Polling Results:")
        print(f"Total polling requests: {total_requests}")
        print(f"Successful polls: {successful_polls}")
        print(f"Rate limited polls: {rate_limited_polls}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Requests per second: {total_requests / total_time:.2f}")
        
        # System should handle polling load reasonably
        assert total_time < 30, "Polling load test should complete in reasonable time"
        assert successful_polls > 0, "Some polling requests should succeed"

    def test_mixed_workload_scenario(self, client, admin_token):
        """Test system behavior under mixed upload and status check workload."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_delay.side_effect = lambda *args: MagicMock(id=f"mixed-task-{time.time()}")
            
            def upload_worker():
                content = b"Mixed workload upload content"
                return client.post(
                    "/api/resumes/upload",
                    files={"file": ("mixed.pdf", io.BytesIO(content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
            
            def status_worker():
                return client.get(
                    "/api/resumes/status/mixed-workload-task",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
            
            # Create mixed workload
            tasks = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                # Submit mix of uploads and status checks
                for i in range(15):
                    if i % 3 == 0:  # Every 3rd request is an upload
                        tasks.append(executor.submit(upload_worker))
                    else:  # Other requests are status checks
                        tasks.append(executor.submit(status_worker))
                
                # Collect results
                results = []
                for future in as_completed(tasks):
                    try:
                        response = future.result()
                        results.append({
                            "status_code": response.status_code,
                            "endpoint": "upload" if "/upload" in str(response.url) else "status"
                        })
                    except Exception as e:
                        results.append({
                            "status_code": None,
                            "endpoint": "unknown",
                            "error": str(e)
                        })
            
            # Analyze mixed workload results
            uploads = [r for r in results if r["endpoint"] == "upload"]
            status_checks = [r for r in results if r["endpoint"] == "status"]
            
            successful_uploads = [r for r in uploads if r["status_code"] == 200]
            successful_status = [r for r in status_checks if r["status_code"] in [200, 404]]
            
            print(f"\nMixed Workload Results:")
            print(f"Upload requests: {len(uploads)} (successful: {len(successful_uploads)})")
            print(f"Status requests: {len(status_checks)} (successful: {len(successful_status)})")
            
            # Both types of operations should work under mixed load
            assert len(results) == 15, "All requests should complete"
            assert len(successful_uploads) + len(successful_status) > 0, "Some requests should succeed"


@pytest.mark.performance
@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Benchmark tests for key performance metrics."""

    def test_auth_token_validation_performance(self, client, admin_token, benchmark):
        """Benchmark JWT token validation performance."""
        
        def validate_token():
            # Test with status endpoint (lightweight operation)
            return client.get(
                "/api/resumes/status/benchmark-task",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        result = benchmark(validate_token)
        
        # Token validation should be fast
        stats = benchmark.stats
        print(f"\nToken Validation Benchmark:")
        print(f"Mean: {stats.mean * 1000:.2f}ms")
        print(f"Min: {stats.min * 1000:.2f}ms")
        print(f"Max: {stats.max * 1000:.2f}ms")
        
        assert stats.mean < 0.1, f"Token validation should be under 100ms, got {stats.mean * 1000:.2f}ms"

    def test_file_validation_performance(self, client, admin_token, benchmark):
        """Benchmark file validation performance."""
        
        def validate_file():
            content = b"%PDF-1.4\nPerformance test content" * 100  # ~3KB file
            
            with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
                mock_delay.return_value = MagicMock(id="perf-task")
                
                return client.post(
                    "/api/resumes/upload",
                    files={"file": ("perf.pdf", io.BytesIO(content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
        
        result = benchmark(validate_file)
        
        stats = benchmark.stats
        print(f"\nFile Validation Benchmark:")
        print(f"Mean: {stats.mean * 1000:.2f}ms")
        print(f"Min: {stats.min * 1000:.2f}ms")
        
        # File validation should be reasonably fast
        assert stats.mean < 0.5, f"File validation should be under 500ms, got {stats.mean * 1000:.2f}ms"

    def test_error_handling_performance(self, client, admin_token, benchmark):
        """Benchmark error handling performance."""
        
        def trigger_error():
            # Upload invalid file type to trigger validation error
            return client.post(
                "/api/resumes/upload",
                files={"file": ("error.txt", io.BytesIO(b"Invalid content"), "text/plain")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        result = benchmark(trigger_error)
        
        # Error handling should be fast
        stats = benchmark.stats
        print(f"\nError Handling Benchmark:")
        print(f"Mean: {stats.mean * 1000:.2f}ms")
        
        assert result.status_code == 400, "Should return validation error"
        assert stats.mean < 0.2, f"Error handling should be under 200ms, got {stats.mean * 1000:.2f}ms"