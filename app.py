def procesar_factura_xml(archivo_subido):
    # Cargar y parsear el XML
    tree = ET.parse(archivo_subido)
    root = tree.getroot()
    ns = {
        'cfdi': 'http://www.sat.gob.mx/cfd/4',
        'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
    }

    # 1. Extracción de Identificadores y Fecha
    emisor = root.find('.//cfdi:Emisor', ns).attrib.get('Nombre', 'Sin emisor')
    receptor = root.find('.//cfdi:Receptor', ns).attrib.get('Nombre', 'Sin receptor')
    
    # Extracción de la fecha de emisión
    fecha_emision = root.attrib.get('Fecha', 'Sin fecha')
    
    tipo_letra = root.attrib.get('TipoDeComprobante', '')
    mapa_comprobantes = {'I': 'Ingreso', 'E': 'Egreso', 'T': 'Traslado', 'P': 'Pago', 'N': 'Nómina'}
    efecto_comprobante = mapa_comprobantes.get(tipo_letra, tipo_letra)
    
    # Múltiples conceptos unidos por <>
    lista_descripciones = [nodo.attrib.get('Descripcion', 'Sin descripción') 
                           for nodo in root.findall('.//cfdi:Conceptos/cfdi:Concepto', ns)]
    descripcion_unida = " <> ".join(lista_descripciones)
    
    folio_fiscal = root.find('.//cfdi:Complemento/tfd:TimbreFiscalDigital', ns).attrib.get('UUID')

    # 2. Extracción de Totales Base
    subtotal = float(root.attrib.get('SubTotal', 0.0))
    descuento = float(root.attrib.get('Descuento', 0.0))
    subtotal_neto = subtotal - descuento
    total_factura = float(root.attrib.get('Total', 0.0))

    # 3. Inicializar variables de impuestos
    iva_trasladado = 0.0
    ieps_trasladado = 0.0
    iva_retenido = 0.0
    isr_retenido = 0.0

    # 4. Búsqueda de Impuestos Globales
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

    # 5. Estructurar la fila con la fecha añadida al final
    fila = {
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
    return fila
