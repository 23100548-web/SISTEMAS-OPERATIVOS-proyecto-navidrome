#!/usr/bin/env python3

import argparse
import csv
import math
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import matplotlib

# Permite generar gráficas sin interfaz gráfica.
matplotlib.use("Agg")
import matplotlib.pyplot as plt


detener = False


# ---------------------------------------------------------
# 1. DETENER CON CTRL+C SIN PERDER LOS RESULTADOS
# ---------------------------------------------------------

def finalizar(signum, frame):
    global detener
    detener = True
    print("\n[+] Finalizando y guardando resultados...")


# ---------------------------------------------------------
# 2. LEER ARCHIVOS DE /proc Y /sys/fs/cgroup
# ---------------------------------------------------------

def leer_clave_valor(ruta):
    """
    Lee archivos con formato:

        Cached: 500000 kB
        MemAvailable: 4000000 kB

    También funciona con memory.stat.
    """

    datos = {}

    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                partes = linea.split()

                if len(partes) >= 2:
                    clave = partes[0].replace(":", "")

                    try:
                        datos[clave] = int(partes[1])
                    except ValueError:
                        pass

    except (FileNotFoundError, PermissionError, OSError):
        pass

    return datos


def leer_entero(ruta):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return int(archivo.read().strip())

    except (
        FileNotFoundError,
        PermissionError,
        ValueError,
        OSError
    ):
        return None


def kib_a_mib(valor):
    if valor is None:
        return None

    return valor / 1024


def bytes_a_mib(valor):
    if valor is None:
        return None

    return valor / (1024 * 1024)


# ---------------------------------------------------------
# 3. LOCALIZAR EL PROCESO Y CGROUP DE NAVIDROME
# ---------------------------------------------------------

def buscar_contenedor(nombre):
    """
    Obtiene el PID principal del contenedor y localiza su cgroup v2.
    """

    try:
        resultado = subprocess.run(
            [
                "podman",
                "inspect",
                "--format",
                "{{.State.Pid}}",
                nombre
            ],
            capture_output=True,
            text=True,
            check=True
        )

        pid = int(resultado.stdout.strip())

        if pid <= 0:
            return None, None

        with open(
            f"/proc/{pid}/cgroup",
            "r",
            encoding="utf-8"
        ) as archivo:

            for linea in archivo:
                jerarquia, controladores, ruta = (
                    linea.strip().split(":", 2)
                )

                # La jerarquía 0 corresponde a cgroups v2.
                if jerarquia == "0":
                    ruta_cgroup = os.path.join(
                        "/sys/fs/cgroup",
                        ruta.lstrip("/")
                    )

                    return pid, ruta_cgroup

    except (
        FileNotFoundError,
        PermissionError,
        ValueError,
        OSError,
        subprocess.SubprocessError
    ):
        pass

    return None, None


# ---------------------------------------------------------
# 4. LEER LAS OPERACIONES DE DISCO DESDE /proc/PID/io
# ---------------------------------------------------------

def leer_bytes_disco_proceso(pid):
    """
    read_bytes indica cuántos bytes causaron lecturas reales desde
    almacenamiento para el proceso.

    Es más útil en este equipo que io.stat, porque Podman rootless
    no muestra BLOCK IO.
    """

    if pid is None:
        return None

    datos_io = leer_clave_valor(f"/proc/{pid}/io")

    return datos_io.get("read_bytes")


# ---------------------------------------------------------
# 5. APLICAR EL ESCENARIO DEL EXPERIMENTO
# ---------------------------------------------------------

def aplicar_escenario(escenario, archivo_audio):
    if escenario == "fria":
        print("\n[EVENTO] Liberando page cache del sistema...")

        subprocess.run(
            ["sync"],
            check=True
        )

        subprocess.run(
            [
                "sudo",
                "sh",
                "-c",
                "echo 3 > /proc/sys/vm/drop_caches"
            ],
            check=True
        )

        print("[EVENTO] drop_caches aplicado.")

    elif escenario == "fadvise":
        if not archivo_audio:
            raise ValueError(
                "Debe indicar --archivo para posix_fadvise"
            )

        if not hasattr(os, "posix_fadvise"):
            raise RuntimeError(
                "Esta versión de Python no incluye posix_fadvise"
            )

        print(
            f"\n[EVENTO] Aplicando POSIX_FADV_DONTNEED a:\n"
            f"{archivo_audio}"
        )

        with open(archivo_audio, "rb") as archivo:
            os.posix_fadvise(
                archivo.fileno(),
                0,
                0,
                os.POSIX_FADV_DONTNEED
            )

        print("[EVENTO] posix_fadvise aplicado.")

    else:
        print(
            "\n[EVENTO] Caché caliente: "
            "no se liberará la caché."
        )


# ---------------------------------------------------------
# 6. AJUSTAR AUTOMÁTICAMENTE LA ESCALA
# ---------------------------------------------------------

def ajustar_escala(eje, valores, margen_minimo=1):
    """
    Amplía visualmente las variaciones pequeñas sin cambiar los datos.
    """

    validos = [
        valor for valor in valores
        if valor is not None
        and not math.isnan(valor)
    ]

    if not validos:
        return

    minimo = min(validos)
    maximo = max(validos)

    rango = max(
        maximo - minimo,
        margen_minimo
    )

    margen = rango * 0.15

    eje.set_ylim(
        max(0, minimo - margen),
        maximo + margen
    )


def obtener_serie(filas, columna):
    serie = []

    for fila in filas:
        valor = fila.get(columna)

        if valor is None or valor == "":
            serie.append(math.nan)
        else:
            serie.append(float(valor))

    return serie


# ---------------------------------------------------------
# 7. GENERAR LAS GRÁFICAS CON ESCALAS INDEPENDIENTES
# ---------------------------------------------------------

def crear_grafica(filas, ruta, fase, tiempo_evento):
    if not filas:
        return

    tiempos = obtener_serie(
        filas,
        "tiempo_s"
    )

    cache_host = obtener_serie(
        filas,
        "cache_host_mib"
    )

    cache_cgroup = obtener_serie(
        filas,
        "cache_cgroup_mib"
    )

    memoria_disponible = obtener_serie(
        filas,
        "memoria_disponible_mib"
    )

    lecturas = obtener_serie(
        filas,
        "lectura_disco_delta_mib"
    )

    figura, graficas = plt.subplots(
        4,
        1,
        figsize=(11, 12),
        sharex=True
    )

    # Gráfica 1: caché global del host.
    graficas[0].plot(
        tiempos,
        cache_host,
        color="blue",
        label="Page cache aproximada del host"
    )

    graficas[0].set_ylabel("MiB")
    graficas[0].set_title("Page cache del host")
    graficas[0].legend()
    graficas[0].grid(alpha=0.3)

    ajustar_escala(
        graficas[0],
        cache_host,
        margen_minimo=5
    )

    # Gráfica 2: caché del cgroup de Navidrome.
    graficas[1].plot(
        tiempos,
        cache_cgroup,
        color="orange",
        label="Caché de archivos del contenedor"
    )

    graficas[1].set_ylabel("MiB")
    graficas[1].set_title("Page cache del contenedor")
    graficas[1].legend()
    graficas[1].grid(alpha=0.3)

    ajustar_escala(
        graficas[1],
        cache_cgroup,
        margen_minimo=1
    )

    # Gráfica 3: memoria disponible.
    graficas[2].plot(
        tiempos,
        memoria_disponible,
        color="green",
        linestyle="--",
        label="Memoria disponible"
    )

    graficas[2].set_ylabel("MiB")
    graficas[2].set_title("Memoria disponible del host")
    graficas[2].legend()
    graficas[2].grid(alpha=0.3)

    ajustar_escala(
        graficas[2],
        memoria_disponible,
        margen_minimo=10
    )

    # Gráfica 4: bytes leídos desde almacenamiento.
    if all(math.isnan(valor) for valor in lecturas):
        graficas[3].text(
            0.5,
            0.5,
            "Lectura de disco no disponible",
            horizontalalignment="center",
            verticalalignment="center",
            transform=graficas[3].transAxes
        )
    else:
        graficas[3].plot(
            tiempos,
            lecturas,
            color="red",
            label="Lecturas físicas del proceso"
        )

        graficas[3].legend()

        ajustar_escala(
            graficas[3],
            lecturas,
            margen_minimo=0.1
        )

    graficas[3].set_ylabel("MiB")
    graficas[3].set_xlabel("Tiempo (segundos)")
    graficas[3].set_title("Lecturas de almacenamiento")
    graficas[3].grid(alpha=0.3)

    # Marca el instante de drop_caches, fadvise o inicio caliente.
    if tiempo_evento is not None:
        for grafica in graficas:
            grafica.axvline(
                tiempo_evento,
                color="black",
                linestyle=":",
                linewidth=1.5,
                label="Evento / inicio de reproducción"
            )

    figura.suptitle(
        f"Experimento Navidrome: {fase}"
    )

    figura.tight_layout(
        rect=[0, 0, 1, 0.97]
    )

    figura.savefig(
        ruta,
        dpi=160,
        bbox_inches="tight"
    )

    plt.close(figura)


# ---------------------------------------------------------
# 8. MOSTRAR DATOS SIN CONVERTIR N/D EN CERO
# ---------------------------------------------------------

def mostrar(valor):
    if valor is None:
        return "N/D"

    return f"{valor:.2f}"


# ---------------------------------------------------------
# 9. PROGRAMA PRINCIPAL
# ---------------------------------------------------------

def main():
    global detener

    parser = argparse.ArgumentParser(
        description="Colector de page cache para Navidrome"
    )

    parser.add_argument(
        "--container",
        default="mi_spotify",
        help="Nombre del contenedor Podman"
    )

    parser.add_argument(
        "--fase",
        required=True,
        help="Ejemplo: fria_256m, caliente_256m o fadvise_256m"
    )

    parser.add_argument(
        "--escenario",
        required=True,
        choices=["fria", "caliente", "fadvise"]
    )

    parser.add_argument(
        "--archivo",
        help="Archivo usado con posix_fadvise"
    )

    parser.add_argument(
        "--duracion",
        type=int,
        default=180,
        help="Duración total del experimento"
    )

    parser.add_argument(
        "--segundo-evento",
        type=int,
        default=10,
        help="Segundo en que se prepara la caché"
    )

    argumentos = parser.parse_args()

    signal.signal(
        signal.SIGINT,
        finalizar
    )

    # Comprobar el contenedor antes de iniciar.
    pid, ruta_cgroup = buscar_contenedor(
        argumentos.container
    )

    if pid is None:
        print(
            f"[ERROR] El contenedor "
            f"'{argumentos.container}' no está ejecutándose."
        )

        return

    print(f"[+] Contenedor: {argumentos.container}")
    print(f"[+] PID: {pid}")
    print(f"[+] Cgroup: {ruta_cgroup}")

    # Solicitar la contraseña antes de iniciar el cronómetro.
    # Así el evento drop_caches no se retrasa esperando la clave.
    if argumentos.escenario == "fria":
        print("[+] Validando permisos para drop_caches...")

        prueba_sudo = subprocess.run(
            ["sudo", "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        if prueba_sudo.returncode != 0:
            subprocess.run(["sudo", "-v"], check=True)

    fase = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        argumentos.fase
    )

    directorio = Path("resultados")
    directorio.mkdir(exist_ok=True)

    fecha = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    ruta_csv = directorio / f"{fecha}_{fase}.csv"
    ruta_grafica = directorio / f"{fecha}_{fase}.png"

    columnas = [
        "timestamp",
        "tiempo_s",
        "fase",
        "evento",
        "cache_host_mib",
        "cache_cgroup_mib",
        "memoria_cgroup_mib",
        "memoria_disponible_mib",
        "lectura_disco_delta_mib"
    ]

    filas = []
    lectura_anterior = None
    evento_aplicado = False
    tiempo_evento = None

    inicio = time.monotonic()

    print("\n============================================")
    print(" COLECTOR DE PAGE CACHE PARA NAVIDROME")
    print("============================================")
    print(f"Fase: {fase}")
    print(
        f"El evento se aplicará en el segundo "
        f"{argumentos.segundo_evento}."
    )
    print("No reproduzca la canción todavía.\n")

    try:
        with open(
            ruta_csv,
            "w",
            newline="",
            encoding="utf-8"
        ) as archivo_csv:

            escritor = csv.DictWriter(
                archivo_csv,
                fieldnames=columnas
            )

            escritor.writeheader()

            while not detener:
                tiempo_s = time.monotonic() - inicio

                if tiempo_s >= argumentos.duracion:
                    break

                evento = ""

                # Aplicar drop_caches, fadvise o escenario caliente
                # mientras el colector ya está funcionando.
                if (
                    not evento_aplicado
                    and tiempo_s >= argumentos.segundo_evento
                ):
                    aplicar_escenario(
                        argumentos.escenario,
                        argumentos.archivo
                    )

                    evento_aplicado = True
                    tiempo_s = time.monotonic() - inicio
                    tiempo_evento = tiempo_s
                    evento = (
                        f"{argumentos.escenario}_"
                        "inicio_reproduccion"
                    )

                    print("\n============================================")
                    print(" REPRODUZCA AHORA LA CANCIÓN DESDE EL INICIO")
                    print("============================================\n")

                # Métricas globales del host.
                meminfo = leer_clave_valor(
                    "/proc/meminfo"
                )

                cached = meminfo.get("Cached")
                shmem = meminfo.get("Shmem", 0)

                if cached is not None:
                    cache_host_kib = max(
                        0,
                        cached - shmem
                    )
                else:
                    cache_host_kib = None

                # Métricas del cgroup.
                if ruta_cgroup:
                    memory_stat = leer_clave_valor(
                        os.path.join(
                            ruta_cgroup,
                            "memory.stat"
                        )
                    )

                    cache_cgroup_bytes = memory_stat.get(
                        "file"
                    )

                    memoria_cgroup_bytes = leer_entero(
                        os.path.join(
                            ruta_cgroup,
                            "memory.current"
                        )
                    )
                else:
                    cache_cgroup_bytes = None
                    memoria_cgroup_bytes = None

                # Lecturas físicas del proceso.
                lectura_actual = leer_bytes_disco_proceso(
                    pid
                )

                if (
                    lectura_actual is not None
                    and lectura_anterior is not None
                ):
                    lectura_delta = max(
                        0,
                        lectura_actual - lectura_anterior
                    )
                else:
                    lectura_delta = None

                lectura_anterior = lectura_actual

                fila = {
                    "timestamp": (
                        datetime.now()
                        .astimezone()
                        .isoformat(timespec="seconds")
                    ),
                    "tiempo_s": round(tiempo_s, 2),
                    "fase": fase,
                    "evento": evento,
                    "cache_host_mib": kib_a_mib(
                        cache_host_kib
                    ),
                    "cache_cgroup_mib": bytes_a_mib(
                        cache_cgroup_bytes
                    ),
                    "memoria_cgroup_mib": bytes_a_mib(
                        memoria_cgroup_bytes
                    ),
                    "memoria_disponible_mib": kib_a_mib(
                        meminfo.get("MemAvailable")
                    ),
                    "lectura_disco_delta_mib": bytes_a_mib(
                        lectura_delta
                    )
                }

                filas.append(fila)
                escritor.writerow(fila)

                # Evita perder los resultados si se interrumpe.
                archivo_csv.flush()

                print(
                    f"{tiempo_s:6.1f}s | "
                    f"Host: "
                    f"{mostrar(fila['cache_host_mib']):>8} MiB | "
                    f"Cgroup: "
                    f"{mostrar(fila['cache_cgroup_mib']):>8} MiB | "
                    f"Lectura: "
                    f"{mostrar(fila['lectura_disco_delta_mib']):>8} MiB"
                )

                time.sleep(1)

    finally:
        crear_grafica(
            filas,
            ruta_grafica,
            fase,
            tiempo_evento
        )

    print("\n[+] Experimento finalizado.")
    print(f"[+] CSV: {ruta_csv}")
    print(f"[+] Gráfica: {ruta_grafica}")


if __name__ == "__main__":
    main()
