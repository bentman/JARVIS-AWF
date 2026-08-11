# WSL/Ubuntu ARM64: replace old Node with Node 24 LTS and make it stick

## Remove apt-installed Node (old 26/22/etc.)
sudo apt purge -y nodejs

## Configure NodeSource for Node 24 LTS
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -

## Install Node 24 ARM64
sudo apt install -y nodejs

## Verify apt has Node 24
apt-cache policy nodejs
/usr/bin/node -v
/usr/bin/node -p "process.arch"

## GOTCHA: NVM may still override /usr/bin/node
type -a node

## If ~/.nvm/... appears first, install/set Node 24 in NVM too
nvm install 24
nvm alias default 24
nvm use 24

## Reload shell and verify it sticks
exec $SHELL -l
node -v
npm -v
node -p "process.arch"