import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

def procesar_factura_xml(archivo_subido):
    nombre_archivo = archivo_subido.name
    
    try:
        contenido_bytes = archivo_subido.getvalue()
        contenido_texto = contenido_bytes.decode('utf-8', errors='ignore')
        root = ET.fromstring(contenido_texto)
        
        # 1. Detectar versión
        version = root.attrib.get('Version') or root.attrib.get('version', '4.0')
        
        # Las versiones 3.2 y 3.3 comparten el mismo namespace base pero 3.2 usaba minúsculas
        ns_cfdi = 'http://www.sat.gob.mx/cfd/3' if version in ['3.2', '3.3'] else 'http://www.sat.gob.mx/cfd/4'
        ns = {
            'cfdi': ns_cfdi,
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
        }

        # 2. Extracciones de datos
        nodo_emisor = root.find('.//cfdi:Emisor', ns)
        emisor = 'Sin emisor'
        if nodo_emisor is not None:
            emisor = nodo_emisor.attrib.get('Nombre') or nodo_emisor.attrib.get('nombre', 'Sin emisor')
        
        nodo_receptor = root.find('.//cfdi:Receptor', ns)
        receptor = 'Sin receptor'
        if nodo_receptor is not None:
            receptor = nodo_receptor.attrib.get('Nombre') or nodo_receptor.attrib.get('nombre', 'Sin receptor')
        
        fecha_emision = root.attrib.get('Fecha') or root.attrib.get('fecha', 'Sin fecha')
        
        # En CFDI 3.2 el comprobante era "ingreso" o "egreso", extraemos solo la primera letra
        tipo_letra = root.attrib.get('TipoDeComprobante') or root.attrib.get('tipoDeComprobante', '')
        letra_inicial = tipo_letra.upper()[0] if tipo_letra else ''
        mapa_comprobantes = {'I': 'Ingreso', 'E': 'Egreso', 'T': 'Traslado', 'P': 'Pago', 'N': 'Nómina'}
        efecto_comprobante = mapa_comprobantes.get(letra_inicial, tipo_letra)
        
        # Conceptos
        lista_descripciones = []
        for nodo in root.findall('.//cfdi:Conceptos/cfdi:Concepto', ns):
            desc = nodo.attrib.get('Descripcion') or nodo.attrib.get('descripcion', 'Sin descripción')
            lista_descripciones.append(desc)
        descripcion_unida = " <> ".join(lista_descripciones) if lista_descripciones else "Sin conceptos"
        
        # Timbre fiscal
        nodo_timbre = root.find('.//cfdi:Complemento/tfd:TimbreFiscalDigital', ns)
        folio_fiscal = 'Sin UUID'
        if nodo_timbre is not None:
            folio_fiscal = nodo_timbre.attrib.get('UUID', 'Sin UUID')

        # 3. Extracción de Totales Base
        subtotal = float(root.attrib.get('SubTotal') or root.attrib.get('subTotal', 0.0))
        descuento = float(root.attrib.get('Descuento') or root.attrib.get('descuento', 0.0))
        subtotal_neto = subtotal - descuento
        total_factura = float(root.attrib.get('Total') or root.attrib.get('total', 0.0))

        # 4. Búsqueda de Impuestos (Mapeando códigos de v4.0 y textos de v3.2)
        iva_trasladado = 0.0
        ieps_trasladado = 0.0
        iva_retenido = 0.0
        isr_retenido = 0.0

        traslados = root.findall('./cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado', ns)
        for t in traslados:
            impuesto = t.attrib.get('Impuesto') or t.attrib.get('impuesto', '')
            importe = float(t.attrib.get('Importe') or t.attrib.get('importe', 0.0))
            
            impuesto = impuesto.upper()
            if impuesto in ['002', 'IVA']:
                iva_trasladado += importe
            elif impuesto in ['003', 'IEPS']:
                ieps_trasladado += importe

        retenciones = root.findall('./cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion', ns)
        for r in retenciones:
            impuesto = r.attrib.get('Impuesto') or r.attrib.get('impuesto', '')
            importe = float(r.attrib.get('Importe') or r.attrib.get('importe', 0.0))
            
            impuesto = impuesto.upper()
            if impuesto in ['002', 'IVA']:
                iva_retenido += importe
            elif impuesto in ['001', 'ISR']:
                isr_retenido += importe

        # 5. Estructurar la fila final
        return {
            "Nombre emisor": emisor,
            "Nombre receptor": receptor,
            "Efecto del comprobante": efecto_comprobante,
            "Descripción": descripcion_unida,
            "Subtotal": subtotal,
            "Descuento": descuento,
            "Subtotal Neto": round(subtotal_neto, 2),
            "IVA Trasladado": round(iva_trasladado, 2),
            "IEPS Trasladado": round(ieps_trasladado, 2),
            "IVA Retenido": round(iva_retenido, 2),
            "ISR Retenido": round(isr_retenido, 2),
            "Total (Calculado)": round(subtotal_neto + iva_trasladado + ieps_trasladado - iva_retenido - isr_retenido, 2),
            "Total (XML)": total_factura,
            "Folio Fiscal": folio_fiscal,
            "Fecha de Emisión": fecha_emision
        }

    except Exception as e:
        # En caso de error, mostramos en el DataFrame qué archivo falló y la razón exacta
        return {
            "Nombre emisor": "ERROR DE LECTURA",
            "Nombre receptor": "ERROR DE LECTURA",
            "Efecto del comprobante": "Desconocido",
            "Descripción": f"El archivo '{nombre_archivo}' falló al leerse: {str(e)}",
            "Subtotal": 0.0,
            "Descuento": 0.0,
            "Subtotal Neto": 0.0,
            "IVA Trasladado": 0.0,
            "IEPS Trasladado": 0.0,
            "IVA Retenido": 0.0,
            "ISR Retenido": 0.0,
            "Total (Calculado)": 0.0,
            "Total (XML)": 0.0,
            "Folio Fiscal": "ERROR",
            "Fecha de Emisión": "ERROR"
        }

def generar_nombre_archivo(archivos_ingresos, archivos_egresos):
    # Valores por defecto en caso de que algo falle
    rfc_cliente = "RFC_DESCONOCIDO"
    mes_str = "MES"
    anio_str = "AÑO"
    
    mapa_meses = {
        '01': 'ENERO', '02': 'FEBRERO', '03': 'MARZO', '04': 'ABRIL',
        '05': 'MAYO', '06': 'JUNIO', '07': 'JULIO', '08': 'AGOSTO',
        '09': 'SEPTIEMBRE', '10': 'OCTUBRE', '11': 'NOVIEMBRE', '12': 'DICIEMBRE'
    }
    
    # Tomamos el primer archivo disponible (prioridad ingresos)
    archivo_muestra = None
    es_ingreso = True
    
    if archivos_ingresos:
        archivo_muestra = archivos_ingresos[0]
    elif archivos_egresos:
        archivo_muestra = archivos_egresos[0]
        es_ingreso = False
        
    if archivo_muestra:
        try:
            # Usamos getvalue() que es seguro y no afecta la lectura posterior
            contenido_texto = archivo_muestra.getvalue().decode('utf-8', errors='ignore')
            root = ET.fromstring(contenido_texto)
            
            # Determinar versión para usar el namespace correcto
            version = root.attrib.get('Version') or root.attrib.get('version', '4.0')
            ns_cfdi = 'http://www.sat.gob.mx/cfd/3' if version in ['3.2', '3.3'] else 'http://www.sat.gob.mx/cfd/4'
            ns = {'cfdi': ns_cfdi}
            
            # 1. Extraer RFC
            if es_ingreso:
                nodo_emisor = root.find('.//cfdi:Emisor', ns)
                if nodo_emisor is not None:
                    rfc_cliente = nodo_emisor.attrib.get('Rfc') or nodo_emisor.attrib.get('rfc', rfc_cliente)
            else:
                # Si solo subieron egresos, la empresa es el receptor
                nodo_receptor = root.find('.//cfdi:Receptor', ns)
                if nodo_receptor is not None:
                    rfc_cliente = nodo_receptor.attrib.get('Rfc') or nodo_receptor.attrib.get('rfc', rfc_cliente)
            
            # 2. Extraer y formatear Fecha (Formato esperado: YYYY-MM-DD...)
            fecha = root.attrib.get('Fecha') or root.attrib.get('fecha')
            if fecha and len(fecha) >= 10:
                anio_str = fecha[0:4]
                mes_num = fecha[5:7]
                mes_str = mapa_meses.get(mes_num, "MES")
                
        except Exception:
            pass # Si este archivo está corrupto, usará los valores por defecto
            
    return f"{rfc_cliente} - {mes_str} {anio_str}.xlsx"

# ==========================================
# INTERFAZ GRÁFICA DE STREAMLIT
# ==========================================

st.title("Procesador Automático de Facturas XML")
st.write("Sube los archivos XML descargados del portal del SAT para generar el reporte en Excel de manera automática.")

# Dividimos la pantalla en dos columnas para mayor claridad
col1, col2 = st.columns(2)

with col1:
    st.subheader("🟢 Comprobantes de Ingreso")
    archivos_ingresos = st.file_uploader("Arrastra aquí los XML de ingresos", type=['xml'], accept_multiple_files=True, key="ing")

with col2:
    st.subheader("🔴 Comprobantes de Egreso")
    archivos_egresos = st.file_uploader("Arrastra aquí los XML de egresos", type=['xml'], accept_multiple_files=True, key="egr")

# Botón central para ejecutar el código
if st.button("Procesar Facturas y Generar Excel", type="primary"):
    
    if not archivos_ingresos and not archivos_egresos:
        st.warning("⚠️ Por favor, sube al menos un archivo XML en alguna de las dos categorías para comenzar.")
    else:
        # Procesamos las listas de archivos
        datos_ing = [procesar_factura_xml(xml) for xml in archivos_ingresos] if archivos_ingresos else []
        datos_egr = [procesar_factura_xml(xml) for xml in archivos_egresos] if archivos_egresos else []
        
        # Convertimos a DataFrames
        df_ingresos = pd.DataFrame(datos_ing)
        df_egresos = pd.DataFrame(datos_egr)
        
        # Guardar en memoria usando io.BytesIO y ExcelWriter para las pestañas
        buffer_memoria = io.BytesIO()
        with pd.ExcelWriter(buffer_memoria, engine='openpyxl') as writer:
            if not df_ingresos.empty:
                df_ingresos.to_excel(writer, index=False, sheet_name='Ingresos')
            if not df_egresos.empty:
                df_egresos.to_excel(writer, index=False, sheet_name='Egresos')
        
        # Obtenemos el archivo creado en la memoria
        archivo_excel_final = buffer_memoria.getvalue()
        
        # GENERAMOS EL NOMBRE DINÁMICO AQUÍ:
        nombre_dinamico = generar_nombre_archivo(archivos_ingresos, archivos_egresos)
        
        st.success("✅ ¡Análisis completado exitosamente! El archivo está listo.")
        
        # Botón para descargar el Excel resultante
        st.download_button(
            label="📥 Descargar Reporte en Excel",
            data=archivo_excel_final,
            file_name=nombre_dinamico, # APLICAMOS EL NOMBRE DINÁMICO
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
