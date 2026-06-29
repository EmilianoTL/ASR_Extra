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

- Subredes derivadas del **subneteo de `8.8.8.0/24`** para los enlaces.
- Los routers arrancan **sin protocolo de enrutamiento** (la app activa RIP/OSPF).
- Solo tienen configuradas y levantadas las IP de sus interfaces.

## Configuración base requerida por router (SNMPv3 + SSH + CDP)

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
