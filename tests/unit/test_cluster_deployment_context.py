# POLICY: frictionless-data-policy-enforcement
from pathlib import Path

def test_docker_build_context_integrity():
    """
    Verifies that the essential files for a cluster Docker build are present
    and in the correct locations relative to the project root.
    """
    project_root = Path(__file__).parent.parent.parent.resolve()
    
    # 1. Essential Docker Directories
    docker_dir = project_root / "docker" / "rpi-worker"
    assert docker_dir.exists(), f"Missing docker/rpi-worker directory at {docker_dir}"
    assert docker_dir.is_dir()
    
    # 2. Main Dockerfile
    docker_file = docker_dir / "Dockerfile"
    assert docker_file.exists(), f"Missing rpi-worker Dockerfile at {docker_file}"
    
    # 3. Essential Source Files (Checked by Dockerfile)
    cocli_dir = project_root / "cocli"
    assert cocli_dir.exists(), "Missing 'cocli' source directory"
    
    pyproject = project_root / "pyproject.toml"
    assert pyproject.exists(), "Missing pyproject.toml"
    
    version_file = project_root / "VERSION"
    assert version_file.exists(), "Missing VERSION file"

def test_cluster_service_root_resolution():
    """
    Verifies that ClusterService correctly identifies the project root 
    for rsync, regardless of where it's called from.
    """
    from cocli.services.cluster_service import ClusterService
    service = ClusterService("roadmap")
    
    # We test the private verification method
    assert service._verify_local_build() is True, "ClusterService failed to verify its own local build context"
