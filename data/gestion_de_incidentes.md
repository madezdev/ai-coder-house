# Proceso de gestión de incidentes

## Cuándo se declara un incidente

Se declara un incidente ante toda alerta P1 o P2, y también cada vez que alguien detecta un impacto en clientes aunque no haya alerta. Cualquier persona de Ingeniería o de Soporte puede declararlo con el comando /incidente en el chat. El comando crea el canal del incidente, con el formato #inc-AAAAMMDD-tema, abre el documento de seguimiento y avisa a la guardia.

Ante la duda, se declara: cerrar un incidente que resultó menor no cuesta nada.

## Roles

Todo incidente P1 tiene tres roles, a cargo de personas distintas:

- **Comandante del incidente**: coordina, decide los próximos pasos y es quien da el incidente por mitigado. Al principio lo asume la guardia primaria, que puede delegarlo si necesita concentrarse en la parte técnica.
- **Responsable de comunicaciones**: actualiza la página de estado y el canal #estado-clientes, y responde a Soporte. No investiga el problema.
- **Escriba**: anota en el documento de seguimiento la línea de tiempo, con la hora de cada hallazgo, decisión y cambio aplicado.

En un P2 el comandante puede ser también el escriba, pero las comunicaciones siguen a cargo de otra persona.

## Comunicación

En un P1, la página de estado se actualiza dentro de los 15 minutos de declarado el incidente y después cada 30 minutos, aunque no haya novedades. En un P2, cada 60 minutos.

Los mensajes describen el impacto para el cliente, qué funciona y qué no. Nunca incluyen nombres de personas, detalles internos de la infraestructura ni horarios de resolución que no estén confirmados.

Si el incidente afecta a clientes con contrato empresarial, el responsable de comunicaciones avisa además a su gerente de cuenta, que se ocupa del contacto directo.

## Mitigar antes de resolver

La prioridad es devolver el servicio, no encontrar la causa. Las mitigaciones preferidas son, en este orden:

1. Revertir el último despliegue.
2. Apagar el feature flag involucrado.
3. Redirigir el tráfico a otra zona.
4. Agregar capacidad.

Cualquier cambio en producción durante un incidente lo aprueba el comandante, y el escriba lo anota.

Un incidente está mitigado cuando terminó el impacto en clientes, y resuelto cuando además se eliminó el riesgo de que se repita en el corto plazo. Entre un estado y otro, el canal del incidente sigue abierto.

## Cierre y postmortem

Todo P1 lleva postmortem. Un P2 también, si duró más de una hora o si se repitió en los últimos 30 días.

El borrador lo escribe el comandante dentro de los 5 días hábiles posteriores al cierre, con la plantilla del equipo: resumen, impacto (duración, clientes y solicitudes afectadas), línea de tiempo, causa raíz, qué funcionó, qué no funcionó y acciones.

Los postmortems son sin culpables: describen cómo el sistema y los procesos permitieron la falla, no quién se equivocó. Se revisan en la reunión semanal de operaciones y se publican en la wiki de Ingeniería, abiertos a toda la empresa.

Cada acción tiene un responsable y una fecha. Las que evitan que un P1 se repita tienen un plazo máximo de 30 días; si no se cumplen, se tratan en la reunión mensual con la gerencia.

## Métricas

El equipo sigue tres métricas por mes: el tiempo hasta el acuse (MTTA), el tiempo hasta la mitigación (MTTM) y la cantidad de incidentes repetidos. Para los P1, el objetivo es un MTTA menor a 5 minutos y un MTTM menor a 60 minutos.
