# PawsRise
# NOTE: THIS IS LINUX ONLY.

A simple python script to connect to Riseup VPN Services
(i suck at making README's)
# How to install:
First. You need OpenVPN. The ways to install it are below.
Then. Download PawsRise.py via git or Direct Download.
# Fedora

sudo dnf update -y

sudo dnf install -y openvpn

# Ubuntu/Debian
sudo apt update

sudo apt install openvpn

# Arch
sudo pacman -Syu

sudo pacman -S openvpn

# Notes
Sometimes. OpenVPN requires you to enable services to make it start and enable it. this is simple as:

sudo systemctl enable openvpn-client@client1.service

sudo systemctl start openvpn-client@client1.service

Now just run PawsRise.py and itll download all the stuff for you. You will select a server and itll connect to it.

(licensed under the apache 2.0 license)

![image](https://github.com/user-attachments/assets/cc0d7e04-b8ee-4886-ac2e-aa28e99db75b)
