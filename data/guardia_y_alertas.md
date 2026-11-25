# Guía de guardia y alertas

## Objetivo

Esta guía define cómo funciona la guardia del equipo de Plataforma: quién atiende las alertas, en cuánto tiempo y cómo se escala cuando nadie responde. Aplica a todos los servicios productivos del catálogo de servicios, incluidos los que mantienen otros equipos pero corren sobre la infraestructura compartida.

## Rotación

La guardia rota cada semana. El turno empieza el lunes a las 10:00 (hora de Buenos Aires) y termina el lunes siguiente a la misma hora. Cada turno tiene dos personas: la guardia primaria, que recibe todas las páginas, y la secundaria, que cubre cuando la primaria no responde o necesita ayuda. Una persona no puede hacer más de dos turnos primarios por mes, y entre dos turnos primarios tiene que haber al menos una semana libre.

El calendario se publica con seis semanas de anticipación en el canal #plataforma-guardia. Los cambios de turno se acuerdan entre las personas involucradas y se cargan en la herramienta de paginado antes de que empiece el turno. Un cambio que solo se acordó por chat no cuenta.

Quien se suma al equipo hace dos turnos como sombra antes de su primer turno como secundaria, y al menos un turno como secundaria antes de ser primaria.

## Severidades

Toda alerta tiene una de cuatro severidades:

- **P1**: el servicio está caído o hay pérdida de datos para los clientes. Por ejemplo, el checkout devuelve errores en más del 5 % de las solicitudes durante 5 minutos, o la base de datos principal no acepta escrituras.
- **P2**: degradación importante con impacto en clientes, pero con el servicio disponible. Por ejemplo, la latencia p95 de la API pública supera los 2 segundos durante 15 minutos.
- **P3**: problema sin impacto inmediato en clientes que se resuelve en horario laboral. Por ejemplo, un disco al 85 % de uso.
- **P4**: aviso informativo. No genera página y se revisa en la reunión semanal de operaciones.

## Tiempos de respuesta

| Severidad | Acuse de recibo | Primera actualización | Horario |
| --- | --- | --- | --- |
| P1 | 5 minutos | 15 minutos | 24 x 7 |
| P2 | 15 minutos | 30 minutos | 24 x 7 |
| P3 | 4 horas hábiles | 1 día hábil | Lunes a viernes, de 9 a 18 |
| P4 | Sin acuse | No aplica | No aplica |

Acusar recibo es tomar la alerta en la herramienta de paginado, no solo leerla en el teléfono. La primera actualización se publica en el canal del incidente y dice qué se sabe, qué se está probando y cuándo llega la próxima actualización.

## Escalamiento

Si la guardia primaria no acusa recibo de una P1 en 5 minutos, la herramienta pagina automáticamente a la secundaria. Si a los 10 minutos sigue sin acuse, pagina a la líder técnica de Plataforma, y a los 20 minutos al gerente de Ingeniería. Para una P2, los mismos escalones se activan a los 15, 30 y 60 minutos.

La guardia puede escalar a mano en cualquier momento: no hace falta esperar a los tiempos automáticos para pedir ayuda. Cuando el problema está en un servicio de otro equipo, se pagina a la guardia de ese equipo desde el mismo incidente, para que quede registrado.

## Alertas ruidosas

Una alerta que se dispara más de tres veces en un turno sin requerir ninguna acción se considera ruidosa. La guardia la etiqueta como "ruido" y abre un ticket para el equipo dueño del servicio, que tiene dos semanas para ajustarla o eliminarla.

Silenciar una alerta está permitido por 24 horas como máximo, siempre con un comentario que explique el motivo. Un silencio más largo necesita la aprobación de la líder técnica.

## Traspaso de turno

Al terminar el turno, la guardia saliente escribe un traspaso en #plataforma-guardia con los incidentes abiertos, las alertas silenciadas y los cambios riesgosos previstos para la semana. La guardia entrante confirma que lo leyó antes de las 12:00 del lunes.

## Compensación

Cada turno primario se compensa con un día libre, que se toma dentro de los 30 días siguientes. Si la guardia atendió una página entre las 0:00 y las 7:00, al día siguiente puede empezar a trabajar a las 12:00 sin descontar horas.
