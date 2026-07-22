import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import io

def procesar_factura_xml(archivo_subido):
    # Guardamos el nombre por si hay un error, saber cuál archivo falló
    nombre_archivo = archivo_subido.name
    
    try:
        # Extraemos y decodificamos a texto plano
        contenido_bytes = archivo_subido.getvalue()
        contenido_texto = contenido_bytes.decode('utf-8', errors='ignore')
        root = ET.fromstring(contenido_texto)
        
        # 1. Detectar versión para adaptar el namespace (3.3 o 4.0)
        version = root.attrib.get('Version', '4.0')
        ns_cfdi = 'http://www.sat.gob.mx/cfd/3' if version == '3.3' else 'http://www.sat.gob.mx/cfd/4'
        
        ns = {
            'cfdi': ns_cfdi,
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
        }

        # 2. Extracciones seguras (Validamos que no sea 'None')
        nodo_emisor = root.find('.//cfdi:Emisor', ns)
        emisor = nodo_emisor.attrib.get('Nombre', 'Sin emisor') if nodo_emisor is not None else 'Sin emisor'
        
        nodo_receptor = root.find('.//cfdi:Receptor', ns)
        receptor = nodo_receptor.attrib.get('Nombre', 'Sin receptor') if nodo_receptor is not None else 'Sin receptor'
        
        fecha_emision = root.attrib.get('Fecha', 'Sin fecha')
        
        tipo_letra = root.attrib.get('TipoDeComprobante', '')
        mapa_comprobantes = {'I': 'Ingreso', 'E': 'Egreso', 'T': 'Traslado', 'P': 'Pago', 'N': 'Nómina'}
        efecto_comprobante = mapa_comprobantes.get(tipo_letra, tipo_letra)
        
        # Conceptos seguros
        lista_descripciones = [nodo.attrib.get('Descripcion', 'Sin descripción') 
                               for nodo in root.findall('.//cfdi:Conceptos/cfdi:Concepto', ns)]
        descripcion_unida = " <> ".join(lista_descripciones) if lista_descripciones else "Sin conceptos"
        
        # Timbre fiscal seguro
        nodo_timbre = root.find('.//cfdi:Complemento/tfd:TimbreFiscalDigital', ns)
        folio_fiscal = nodo_timbre.attrib.get('UUID', 'Sin UUID') if nodo_timbre is not None else 'Sin UUID'

        # 3. Extracción de Totales Base
        subtotal = float(root.attrib.get('SubTotal', 0.0))
        descuento = float(root.attrib.get('Descuento', 0.0))
        subtotal_neto = subtotal - descuento
        total_factura = float(root.attrib.get('Total', 0.0))

        # 4. Búsqueda de Impuestos Globales
        iva_trasladado = 0.0
        ieps_trasladado = 0.0
        iva_retenido = 0.0
        isr_retenido = 0.0

        traslados = root.findall('./cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado', ns)
        for t in traslados:
            impuesto = t.attrib.get('Impuesto')
            importe = float(t.attrib.get('Importe', 0.0))
            if impuesto == '002':
                iva_trasladado += importe
            elif impuesto == '003':
                ieps_trasladado += importe

        retenciones = root.findall('./cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion', ns)
        for r in retenciones:
            impuesto = r.attrib.get('Impuesto')
            importe = float(r.attrib.get('Importe', 0.0))
            if impuesto == '002':
                iva_retenido += importe
            elif impuesto == '001':
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
        # Si ocurre CUALQUIER error de formato, generamos una fila de alerta sin apagar la app
        return {
            "Nombre emisor": "ERROR DE LECTURA",
            "Nombre receptor": "ERROR DE LECTURA",
            "Efecto del comprobante": "Desconocido",
            "Descripción": f"El archivo '{nombre_archivo}' no es una factura válida o está dañado.",
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
        
        st.success("✅ ¡Análisis completado exitosamente! El archivo está listo.")
        
        # Botón para descargar el Excel resultante
        st.download_button(
            label="📥 Descargar Reporte en Excel",
            data=archivo_excel_final,
            file_name="Reporte_Mensual_Facturas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
