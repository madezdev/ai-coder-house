# Respaldos y recuperación ante desastres

## Qué se respalda

Se respaldan las bases de datos PostgreSQL de producción, los buckets con los archivos que suben los clientes y la configuración de la infraestructura. El código no se respalda aparte porque vive en el repositorio y sus réplicas. Las cachés de Redis tampoco: se reconstruyen a partir de las bases de datos.

## Bases de datos

Cada base PostgreSQL de producción tiene:

- Un respaldo completo diario a las 03:00 (hora de Buenos Aires), cuando el tráfico es mínimo.
- Archivado continuo del registro de transacciones (WAL), que permite recuperar la base en cualquier punto de los últimos 7 días.
- Una réplica en otra región, que se usa solo como contingencia y no recibe consultas de las aplicaciones.

Los respaldos completos diarios se guardan 35 días. El del primer día de cada mes se guarda 12 meses, y el del 1 de enero, 5 años, por requisitos contables.

## Archivos de clientes

Los buckets tienen el versionado activado: un archivo borrado o sobrescrito se puede recuperar durante 30 días. Además, una copia diaria se replica a un bucket en otra región, en una cuenta separada a la que solo acceden dos personas del equipo de Seguridad. Así, si se filtran las credenciales de producción, los respaldos siguen a salvo.

## Cifrado y acceso

Todos los respaldos se guardan cifrados con claves que administra el equipo de Seguridad y que rota una vez por año.

Restaurar un respaldo en producción necesita la aprobación de dos personas: quien ejecuta la restauración y la líder técnica de Plataforma o, si no está, el gerente de Ingeniería. Restaurar en un ambiente de prueba solo necesita un ticket.

Los respaldos de producción nunca se restauran en computadoras personales: los datos de clientes solo se manejan en los ambientes autorizados.

## Objetivos de recuperación

| Sistema | RPO (pérdida máxima de datos) | RTO (tiempo máximo de recuperación) |
| --- | --- | --- |
| Base de pedidos y pagos | 15 minutos | 1 hora |
| Resto de las bases de datos | 1 hora | 4 horas |
| Archivos de clientes | 24 horas | 8 horas |

La base de pedidos y pagos tiene un RPO menor porque su WAL se envía cada 5 minutos en lugar de cada 30.

## Pruebas de restauración

Un respaldo que nunca se restauró no cuenta como respaldo. Por eso:

- Todos los lunes, un proceso automático restaura el último respaldo completo de cada base en un ambiente aislado y compara la cantidad de filas de las tablas principales con producción. Si algo no coincide, genera una alerta P3.
- Una vez por trimestre se hace un simulacro de desastre: se elige una base al azar y se la recupera desde cero en otra región, midiendo cuánto tarda. El tiempo se compara con el RTO de la tabla anterior y, si lo supera, se abre una acción con 30 días de plazo.

## Recuperación ante un desastre

Si se pierde una región completa, la guardia declara un incidente P1 y el comandante decide pasar a la región de contingencia. La réplica de la base se promueve a principal, se actualizan los registros DNS y se redirige el tráfico. El paso a paso, con los comandos, está en el runbook "Conmutación de región", que se revisa en cada simulacro trimestral.

Volver a la región original no es urgente. Se planifica como un cambio normal, dentro de una ventana de despliegue, cuando la región lleva al menos 48 horas estable.
