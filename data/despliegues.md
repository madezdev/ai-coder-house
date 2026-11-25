# Política de despliegues

## Alcance

Esta política aplica a todo cambio que llega a producción: código de los servicios, configuración, migraciones de base de datos y cambios de infraestructura. No incluye los cambios de contenido que se hacen desde el panel de administración.

## Requisitos antes de desplegar

Un cambio puede ir a producción cuando cumple todo esto:

- Tiene un pull request aprobado por al menos una persona que no sea quien lo escribió. Si toca pagos, autenticación o datos personales, necesita dos aprobaciones.
- Pasó la integración continua completa: tests, análisis estático y escaneo de dependencias.
- Estuvo al menos 2 horas en staging sin errores nuevos.
- Si trae una migración de base de datos, la migración es compatible con la versión anterior del código, así el despliegue se puede revertir sin revertir la migración.

## Ventanas de despliegue

Los despliegues normales se hacen de lunes a jueves entre las 10:00 y las 17:00, y los viernes entre las 10:00 y las 13:00 (hora de Buenos Aires). Fuera de esas ventanas solo se despliegan correcciones de incidentes P1 o P2, con la aprobación del comandante del incidente.

Hay dos períodos de congelamiento en los que no se despliega nada salvo correcciones de incidentes:

- Desde el lunes anterior al Black Friday hasta el miércoles posterior al Cyber Monday.
- Del 20 de diciembre al 3 de enero.

Durante un congelamiento, cualquier excepción la aprueba el gerente de Ingeniería por escrito en el canal #despliegues.

## Despliegue progresivo

Los servicios con tráfico de clientes se despliegan en tres etapas:

1. **Canary**: la versión nueva recibe el 5 % del tráfico durante 30 minutos.
2. **Ampliación**: si el canary está sano, pasa al 50 % durante 15 minutos.
3. **Completo**: el 100 % del tráfico.

El paso de una etapa a otra es automático. El despliegue se frena y vuelve a la versión anterior si, en cualquier etapa, la tasa de errores 5xx de la versión nueva supera el 2 %, la latencia p95 empeora más de un 20 % respecto de la versión estable o se dispara una alerta P1 del servicio.

Los servicios internos, sin tráfico de clientes, pueden desplegarse en una sola etapa.

## Rollback

Cualquier persona del equipo puede revertir un despliegue sin pedir permiso si sospecha que causó un problema: revertir de más cuesta poco. Se hace con el botón "Volver a la versión anterior" del pipeline y tarda unos 4 minutos. Después de revertir se avisa en #despliegues y, si hubo impacto en clientes, se declara un incidente.

Una versión revertida no se vuelve a desplegar hasta que se entienda la causa y haya un test que la habría detectado.

## Feature flags

Las funcionalidades nuevas que cambian lo que ven los clientes salen detrás de un feature flag, apagado por defecto. El flag se enciende de a poco (1 %, 10 %, 50 % y 100 %) y tiene un responsable. Cuando lleva 90 días encendido al 100 %, se saca del código junto con el camino viejo.

## Registro

Cada despliegue queda registrado automáticamente en #despliegues con el servicio, la versión, quién lo lanzó y el enlace al pull request. Es lo primero que se consulta al investigar un incidente.
