# Windows ARM64: replace old Node with Node 24 LTS and make it stick

## Remove current Node install
winget uninstall OpenJS.NodeJS
winget uninstall OpenJS.NodeJS.LTS

## Confirm the LTS package is Node 24
winget search OpenJS.NodeJS.LTS

## Install native ARM64 Node 24 LTS explicitly
winget install -e --id OpenJS.NodeJS.LTS --architecture arm64

## Verify version + architecture
node -v
npm -v
node -p "process.arch"
where.exe node