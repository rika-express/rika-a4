TERMINALS={'delivered':'delivery','mailbox':'delivery','return':'return','destruction':'destruction'}

def completion(event):
    return 'delivery' if event.get('type')=='visit' and event.get('result')=='delivered' else TERMINALS.get(event.get('type'))

def resolve_catalog(value):
    """Reuse existing fields and phrases without maintaining a second handover template."""
    from copy import deepcopy
    for spec in value['types'].values():
        for key,result in list(spec['results'].items()):
            if 'use_result' in result:
                typ,res=result['use_result']
                spec['results'][key]={**deepcopy(value['types'][typ]['results'][res]),**result}
    return value
