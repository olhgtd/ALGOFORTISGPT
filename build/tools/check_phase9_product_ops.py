from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'dashboard'/'backend'/'product_ops_v2'
forbidden=('engine.broker_adapters','engine.live','Approved'+'Order(','arm_'+'live','place_'+'order','modify_'+'order','cancel_'+'order')
violations=[]
for p in TARGET.glob('*.py'):
    text=p.read_text(encoding='utf-8')
    low=text.lower()
    for token in forbidden:
        if token.lower() in low: violations.append(f'{p.relative_to(ROOT)}:{token}')
if violations:
    raise SystemExit('PHASE9_PRODUCT_OPS_STATIC_FAIL\n'+'\n'.join(violations))
print('PHASE9_PRODUCT_OPS_STATIC_PASS')
