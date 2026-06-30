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

### Direccionamiento de ejemplo (ajustable)

| Dispositivo | Core 8.8.8.0/24 (vía Sw1) | LAN propia | Notas |
|-------------|---------------------------|------------|-------|
| R1 | f0/0 = 8.8.8.1 | f0/1 = 148.204.56.1/24 | `ip_admin` (para el sistema) = **8.8.8.1** |
| R2 | f0/0 = 8.8.8.5 | f0/1 = 148.204.59.1/24 | `ip_admin` = **8.8.8.5** |
| R3 | f0/0 = 8.8.8.9 | f0/1 = 148.204.60.1/24 | `ip_admin` = **8.8.8.9** |
| SME | eth0 = 8.8.8.100 | — | eth1 por DHCP (NAT). Destino de traps |
| PC1 | — | 148.204.59.10 (gw .1) | en LAN de R2 |
| PC2 | — | 148.204.60.10 (gw .1) | en LAN de R3 |

> El **core 8.8.8.0/24** es un segmento compartido por Sw1: R1/R2/R3 y la SME están
> directamente conectados, así que el **polling y los traps SNMP funcionan sin
> necesidad de protocolo de enrutamiento**. Las LAN de cada router se alcanzan desde
> la SME mediante rutas estáticas vía el core (ver `configs/EndDevices/SME/`).
> El `ip_admin` que usará el sistema es la **IP de cada router en el core**.

## Configuraciones incluidas

- `configs/R1|R2|R3/Rx_startup-config.cfg` — config completa de cada router.
- `configs/EndDevices/SME/` — red de la SME + scripts (`setup_sme.sh`,
  `sync_github.sh`, `sme-routes.sh`). Ver su README para el detalle.
- `configs/EndDevices/PC1|PC2/*.vpc` — direccionamiento de los VPCS.

## Configuración base requerida por router (SNMPv3 + SSH + CDP)

> El comando `crypto key generate rsa modulus 1024` es de modo config interactivo
> (genera la llave para SSH) y **no** aparece en el `startup-config`; ejecútalo a mano
> una vez por router después de definir `hostname` e `ip domain-name`.

```
! SNMPv3 (SHA + AES128)
snmp-server group GRUPO_V3 v3 priv
snmp-server user snmp_user GRUPO_V3 v3 auth sha authpass123 priv aes 128 privpass123
snmp-server enable traps
snmp-server host <IP_MV_ALPINE> version 3 priv snmp_user
snmp-server location <ubicacion>
snmp-server contact <contacto>
! CDP para descubrimiento de topología
cdp run
! SSH para Ansible/Netmiko
hostname R1
ip domain-name lab.local
crypto key generate rsa modulus 1024
username admin privilege 15 secret cisco123
enable secret enable123
line vty 0 4
 transport input ssh
 login local
! NOTA: SIN 'router rip' / 'router ospf' (la app los activa)
```
