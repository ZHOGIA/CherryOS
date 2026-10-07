# Cara Pakai cherryOS Miner di Linux

Panduan ini ditulis untuk Ubuntu/Debian. Jalankan miner hanya pada komputer
yang Anda miliki atau yang memang Anda mendapat izin untuk gunakan.

## 1. Update sistem

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git ca-certificates python3 python3-venv python3-pip vulkan-tools
```

Jangan menjalankan miner sebagai `root`. Buat dan gunakan user Linux biasa.

## 2. Pasang driver GPU

### NVIDIA

Untuk Ubuntu, gunakan driver dari repository distribusi Linux:

```bash
sudo ubuntu-drivers devices
sudo ubuntu-drivers autoinstall
sudo reboot
```

Untuk Debian, pastikan repository `contrib`, `non-free`, dan `non-free-firmware`
sudah aktif, lalu jalankan:

```bash
sudo apt update
sudo apt install -y linux-headers-amd64 nvidia-driver firmware-misc-nonfree
sudo reboot
```

Setelah masuk kembali:

```bash
nvidia-smi
vulkaninfo --summary
```

Jika `nvidia-smi` gagal, selesaikan masalah driver terlebih dahulu. Jika
`vulkaninfo` tidak menemukan adapter, backend GPU belum siap.

### AMD atau Intel

```bash
sudo apt install -y mesa-vulkan-drivers
sudo reboot
vulkaninfo --summary
```

Nama paket driver dapat berbeda menurut versi distribusi Linux dan model GPU.

## 3. Upload source code ke GitHub

GitHub + Git adalah pilihan yang disarankan karena menyimpan histori perubahan
dan memudahkan update di server Linux. Buat repository baru di GitHub, sebaiknya
private, tanpa menambahkan README atau `.gitignore` otomatis.

Di folder project Windows, buka PowerShell lalu jalankan:

```powershell
git init
git branch -M main
git add cherryos_miner.py requirements-gpu.txt README.md "cara pakai.md"
git commit -m "Add cherryOS Linux GPU miner"
git remote add origin https://github.com/USERNAME/NAMA-REPO.git
git push -u origin main
```

Ganti `USERNAME/NAMA-REPO` dengan repository milik Anda. Saat GitHub meminta
login melalui HTTPS, gunakan GitHub CLI atau Personal Access Token, bukan
password akun biasa. SSH juga dapat digunakan:

```powershell
git remote set-url origin git@github.com:USERNAME/NAMA-REPO.git
git push -u origin main
```

Jangan masukkan private key, token, password, atau file `.env` ke repository.
Alamat wallet publik boleh digunakan sebagai argumen saat menjalankan miner,
tetapi tidak perlu ditulis ke source code.

## 4. Clone di mesin Linux

```bash
git clone https://github.com/USERNAME/NAMA-REPO.git
cd NAMA-REPO
```

Jika repository private dan SSH sudah dikonfigurasi:

```bash
git clone git@github.com:USERNAME/NAMA-REPO.git
cd NAMA-REPO
```

## 5. Buat Python virtual environment

Virtual environment menjaga dependency project tetap terpisah dari Python
sistem:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-gpu.txt
```

Pastikan GPU dapat dibaca oleh `wgpu`:

```bash
python -c "import wgpu; a=wgpu.gpu.request_adapter_sync(power_preference='high-performance'); print(a.info if a else 'GPU adapter tidak ditemukan')"
```

## 6. Cek coordinator

Ganti alamat di bawah dengan wallet publik Anda:

```bash
python cherryos_miner.py \
  --wallet 0xALAMAT_WALLET_40_HEX \
  --check
```

Mode `--check` hanya memeriksa coordinator dan mengambil challenge. Mode ini
belum melakukan mining.

## 7. Jalankan dengan GPU

```bash
python cherryos_miner.py \
  --wallet 0xALAMAT_WALLET_40_HEX \
  --backend gpu \
  --intensity 0.75
```

Nilai `--intensity` berada di antara `0.05` dan `1.0`. Gunakan nilai lebih
rendah untuk mengurangi beban GPU. Untuk memilih GPU otomatis dan memakai CPU
jika GPU tidak tersedia:

```bash
python cherryos_miner.py \
  --wallet 0xALAMAT_WALLET_40_HEX \
  --backend auto
```

Untuk menghentikan miner, tekan `Ctrl+C`. Miner akan mencoba mengirim share
yang masih tertunda sebelum berhenti.

## 8. Menjalankan melalui tmux

`tmux` menjaga proses tetap berjalan ketika koneksi SSH terputus:

```bash
sudo apt install -y tmux
tmux new -s cherryos
source .venv/bin/activate
python cherryos_miner.py --wallet 0xALAMAT_WALLET_40_HEX --backend gpu --intensity 0.75
```

Tekan `Ctrl+B`, lalu `D` untuk keluar dari sesi tanpa menghentikan miner.
Untuk kembali melihatnya:

```bash
tmux attach -t cherryos
```

## 9. Update versi dari GitHub

Jika source code berubah:

```bash
cd ~/NAMA-REPO
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements-gpu.txt --upgrade
```

Hentikan proses miner lama sebelum menjalankan versi baru.

## Alternatif tanpa GitHub

Untuk upload langsung ke server Linux, gunakan `scp` dari PowerShell:

```powershell
scp -r .\cherryos USER@SERVER:~/cherryos
```

GitHub tetap lebih baik untuk penggunaan berulang karena update cukup memakai
`git pull` dan setiap perubahan memiliki histori.
