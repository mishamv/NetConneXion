Write-Host "Repo root:"; git rev-parse --show-toplevel
Write-Host "Branch:"; git branch --show-current
Write-Host "Commit:"; git rev-parse --short HEAD
Write-Host "Python:"; python -V
Write-Host "Executable:"; python -c "import sys; print(sys.executable)"