# Infraestructura — Topología GNS3

Esta carpeta guarda **las exportaciones de GNS3** y las configuraciones de los
dispositivos de la red del examen. Es documentación/respaldo de la topología; el
sistema **no lee** estos archivos en tiempo de ejecución (la topología se descubre
dinámicamente por CDP/SNMP).

## Estructura

```
Infrastructure/
├── README.md
├── Topologia/                 # Exportación del proyecto GNS3 (.gns3 + recursos)
│   └── (aquí va tu export de GNS3)
└── configs/                   # startup-config de cada dispositivo
    ├── R1/                    # Cisco c7200
    ├── R2/                    # Cisco c7200
    ├── R3/                    # Cisco c7200
    ├── Sw1/                   # Switch simple (sin IP)
    └── EndDevices/
        ├── PC1/
        ├── PC2/
        └── SME/               # MV Alpine Linux que aloja el sistema
```

> Coloca aquí la exportación de tu proyecto GNS3 (carpeta `Topologia/`) y el
> `startup-config` de cada router en su subcarpeta de `configs/`.

## Topología del examen

| Dispositivo | Tipo | Rol |
|-------------|------|-----|
| R1, R2, R3 | Cisco c7200 (IOS) | Routers a monitorear/configurar |
| Sw1 | Switch | Conmutación L2 (sin IP) |
| PC1, PC2 | VPCS | Hosts finales |
| SME | Alpine Linux | MV que corre el backend Flask + frontend Astro |

- Los routers arrancan **sin protocolo de enrutamiento** (la app activa RIP/OSPF).
- Solo tienen configuradas y levantadas las IP de sus interfaces.

### Enlaces inter-router con subneteo /30 (punto a punto)

Topología en **cadena**: **R1 — R2 — R3** (R2 en medio; R1 y R3 NO están
conectados entre sí). Los enlaces se subnetean a **/30** (2 hosts por enlace)
desde `8.8.8.0/24`:

| Enlace | Subred /30 | Extremo A | Extremo B |
|--------|-----------|-----------|-----------|
| R1 ↔ R2 | `8.8.8.0/30` | R1 f1/0 = **8.8.8.1** | R2 f1/0 = 8.8.8.2 |
| R2 ↔ R3 | `8.8.8.4/30` | R2 f1/1 = **8.8.8.5** | R3 f1/1 = 8.8.8.6 |

### LANs y hosts (ajustable)

| Dispositivo | Interfaz LAN | IP | Notas |
|-------------|--------------|----|-------|
| R1 | f0/0 | 148.204.56.1/24 | LAN de gestión (aloja la SME, vía Switch1) |
| R2 | f0/0 | 148.204.59.1/24 | aloja PC1 |
| R3 | f0/0 | 148.204.60.1/24 | aloja PC2 |
| SME | eth0 | 148.204.56.10/24 | eth1 por DHCP (NAT). Destino de traps |
| PC1 | — | 148.204.59.10 (gw .1) | en LAN de R2 (R2 f0/0) |
| PC2 | — | 148.204.60.10 (gw .1) | en LAN de R3 (R3 f0/0) |

> Con enlaces **/30 punto a punto no hay segmento compartido** entre los tres
> routers. La **SME cuelga de la LAN de R1** y alcanza a R2/R3 a través de R1 una vez
> que la app activa el enrutamiento (RIP/OSPF). El examen configura el enrutamiento
> **antes** de explorar/monitorear, así que el orden es consistente.
> El `ip_admin` que use el sistema para cada router será una IP suya alcanzable
> (R1: 148.204.56.1 directa; R2/R3: vía R1 tras el enrutamiento). El descubrimiento
> CDP poblará las IPs reales.

## Configuraciones incluidas

- `configs/R1|R2|R3/Rx_startup-config.cfg` — config completa de cada router.
- `configs/EndDevices/SME/` — red de la SME + scripts (`setup_sme.sh`,
  `sync_github.sh`, `sme-routes.sh`). Ver su README para el detalle.
- `configs/EndDevices/PC1|PC2/*.vpc` — direccionamiento de los VPCS.

## Configuración base requerida por router (SNMPv3 + SSH + CDP)

> **Copia y pega por comandos:** usa los archivos `configs/Rx/Rx_comandos.txt`
> (sin comentarios, ya incluyen `configure terminal` … `end` / `write memory`).
>
> Notas del lab (c7200 IOS):
> - La llave SSH se genera con `crypto key generate rsa general-keys modulus 1024`
>   (después de fijar `hostname` e `ip domain-name`).
> - El protocolo de privacidad SNMPv3 que acepta el equipo es **DES56** (no AES128).

```
! SNMPv3 (SHA + DES56)
snmp-server group GRUPO_V3 v3 priv
snmp-server user snmp_user GRUPO_V3 v3 auth sha authpass123 priv des56 privpass123
snmp-server enable traps
snmp-server host <IP_MV_ALPINE> version 3 priv snmp_user
snmp-server location <ubicacion>
snmp-server contact <contacto>
! CDP para descubrimiento de topología
cdp run
! SSH para Ansible/Netmiko
hostname R1
ip domain-name lab.local
crypto key generate rsa general-keys modulus 1024
username admin privilege 15 secret cisco123
enable secret enable123
line vty 0 4
 transport input ssh
 login local
! NOTA: SIN 'router rip' / 'router ospf' (la app los activa)
```
