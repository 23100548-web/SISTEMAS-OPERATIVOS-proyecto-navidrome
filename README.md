# Proyecto del Curso: Sistemas Operativos I (V Ciclo)
**Tema Protagonista:** Tu propio Spotify (Navidrome) – Instrumentación de Page Cache y Buffering
**Institución:** Universidad ESAN
**Profesor:** Marks Calderon Niquin

## Integrantes
* Janampa Diaz Gustavo David
* Lora Sambrano Jean Paul
* Llerena Cabrera Anthony Paolo
* Quispe Inge Kevin Henry

---

## Despliegue de la Aplicación (Podman Rootless)
Para cumplir con los requisitos obligatorios de aislamiento de recursos, entorno rootless y configuración de cgroups v2, el contenedor se desplegó ejecutando el siguiente comando en la terminal de Ubuntu:

```bash
podman run -d \
  --name mi_spotify \
  -p 4533:4533 \
  -v ~/navidrome/data:/data:Z \
  -v ~/navidrome/music:/music:Z \
  -e ND_LOGLEVEL=info \
  -e ND_SCANINTERVAL=1m \
  --memory=256m \
  --memory-swap=256m \
  docker.io/deluan/navidrome:latest
