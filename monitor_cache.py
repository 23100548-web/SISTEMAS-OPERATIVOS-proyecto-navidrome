import time
import os
import csv
import matplotlib.pyplot as plt

def obtener_metricas_cache():
    meminfo = {}
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                meminfo[parts[0].replace(':', '')] = int(parts[1])
    
    cache_total = meminfo.get('Cached', 0) + meminfo.get('Buffers', 0)
    mem_libre = meminfo.get('MemFree', 0)
    return cache_total / 1024, mem_libre / 1024  # Retorna en MB

print("      COLECTOR PROGRAMADO: MONITOREO PAGE CACHE        ")


tiempos = []
caches = []
libres = []

try:
    print(f"{'Tiempo (s)':<12}{'Page Cache (MB)':<18}{'Mem. Libre (MB)':<18}")
    print("-" * 50)
    
    segundo = 0
    while True:
        cache, libre = obtener_metricas_cache()
        print(f"{segundo:<12}{cache:<18.2f}{libre:<18.2f}")
        
        # Guardar en las listas para graficar
        tiempos.append(segundo)
        caches.append(cache)
        libres.append(libre)
        
        time.sleep(1)
        segundo += 1

except KeyboardInterrupt:
    print("\n[+] Grabando datos del experimento...")
    
    # 1. Guardar a CSV (Entregable de instrumentación)
    with open('resultado_experimento.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Tiempo (s)', 'Page Cache (MB)', 'Memoria Libre (MB)'])
        writer.writerows(zip(tiempos, caches, libres))
    print("[Archivo 'resultado_experimento.csv' guardado.")
    
    # 2. Generar el Gráfico Automático (Para las diapositivas e informe)
    plt.figure(figsize=(10, 5))
    plt.plot(tiempos, caches, label='Page Cache (RAM)', color='blue', linewidth=2)
    plt.plot(tiempos, libres, label='Memoria Libre', color='green', linestyle='--')
    plt.xlabel('Tiempo (segundos)')
    plt.ylabel('Megabytes (MB)')
    plt.title('Impacto del Streaming de Navidrome en la Page Cache de Linux')
    plt.legend()
    plt.grid(True)
    
    # Guardar gráfico como imagen
    plt.savefig('grafico_page_cache.png')
    print("Gráfico 'grafico_page_cache.png' generado.")
    print("=======================================================")
