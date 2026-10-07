# Instalasi Linux GPU Miner

Panduan ini berfokus pada Ubuntu/Debian dengan GPU NVIDIA. Gunakan user Linux
biasa, bukan `root`, saat menjalankan miner.

## 1. Update sistem

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git build-essential vulkan-tools
```

## 2. Instal Python

```bash
sudo apt install -y python3 python3-pip python3-venv
python3 --version
python3 -m pip --version
```

Python 3.10 atau lebih baru disarankan.

## 3. Instal driver NVIDIA di Ubuntu

```bash
sudo apt install -y ubuntu-drivers-common
ubuntu-drivers devices
sudo ubuntu-drivers autoinstall
sudo reboot
```

Setelah reboot, verifikasi driver:

```bash
nvidia-smi
```

Jika perintah tersebut menampilkan model GPU dan versi driver, driver NVIDIA
sudah aktif.

## 4. Instal driver NVIDIA di Debian

Aktifkan repository `contrib`, `non-free`, dan `non-free-firmware` terlebih
dahulu. Kemudian jalankan:

```bash
sudo apt update
sudo apt install -y linux-headers-amd64 nvidia-driver firmware-misc-nonfree
sudo reboot
```

Verifikasi setelah reboot:

```bash
nvidia-smi
```

Jika `linux-headers-amd64` tidak sesuai dengan kernel yang digunakan, pasang
paket header yang sesuai dengan kernel Anda sebelum memasang driver NVIDIA.

## 5. Verifikasi Vulkan

Backend GPU miner menggunakan WebGPU melalui Vulkan. Pastikan adapter NVIDIA
terlihat:

```bash
vulkaninfo --summary
```

Output harus memuat adapter NVIDIA. Jika `nvidia-smi` berhasil tetapi Vulkan
tidak menemukan adapter, pasang loader Vulkan:

```bash
sudo apt install -y libvulkan1 vulkan-tools
```

Kemudian reboot dan jalankan `vulkaninfo --summary` kembali.

## 6. Ambil source code

Dengan GitHub:

```bash
git clone https://github.com/USERNAME/NAMA-REPO.git
cd NAMA-REPO
```

Ganti `USERNAME/NAMA-REPO` dengan repository Anda.

## 7. Instal dependency GPU project

Buat virtual environment agar dependency tidak mengganggu Python sistem:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-gpu.txt
```

Pastikan Python dapat melihat adapter NVIDIA melalui `wgpu`:

```bash
python -c "import wgpu; a=wgpu.gpu.request_adapter_sync(power_preference='high-performance'); print(a.info if a else 'GPU adapter tidak ditemukan')"
```

## 8. Uji coordinator

Gunakan alamat wallet publik Anda. Jangan masukkan private key:

```bash
python cherryos_miner.py \
  --wallet 0xALAMAT_WALLET_40_HEX \
  --check
```

Perintah ini hanya menguji koneksi dan mengambil challenge. Belum ada proses
mining.

## 9. Jalankan miner dengan GPU

```bash
python cherryos_miner.py \
  --wallet 0xALAMAT_WALLET_40_HEX \
  --backend gpu \
  --intensity 0.75
```

Gunakan nilai `--intensity` antara `0.05` dan `1.0`. Nilai yang lebih rendah
mengurangi beban GPU. Hentikan proses dengan `Ctrl+C`.

## Masalah umum

### `nvidia-smi: command not found`

Driver NVIDIA belum terpasang atau sistem belum reboot setelah instalasi.
Ulangi langkah driver sesuai distribusi Linux yang digunakan.

### `GPU adapter tidak ditemukan`

Pastikan `nvidia-smi` dan `vulkaninfo --summary` sama-sama mendeteksi GPU.
Periksa juga bahwa dependency dipasang di virtual environment yang sedang
aktif:

```bash
source .venv/bin/activate
python -m pip show wgpu
```

### `wgpu` gagal dibuat

Pastikan driver GPU, loader Vulkan, dan `vulkan-tools` berasal dari instalasi
sistem yang sama. Jalankan ulang:

```bash
sudo apt install --reinstall -y libvulkan1 vulkan-tools
vulkaninfo --summary
```
