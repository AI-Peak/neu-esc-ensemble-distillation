"""Opt-in checkpoint acceptance. Model source is read only, hash-verified then copied."""
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time
import unicodedata

import pytest

from services.attribution import (align_and_group, generate_permutations,
    evaluate_coalition_outputs, target_value, compute_shapley_from_coalition_map)
from services.attribution_contract import check_parity
from services.inference.registry import ModelRegistry, profiles
from tests.inference.test_three_layer_real_model import _verify_and_copy_active_bundle

# Author-written inputs; intended categories do not determine actual model labels.
CASES = [
    "Thư viện sáng sủa nhưng wifi mất kết nối mỗi buổi chiều.",
    "Nhân viên phòng đào tạo hướng dẫn hồ sơ rất rõ ràng.",
    "Máy chiếu nhòe và điều hòa phòng học không hoạt động.",
    "Lịch thi học kỳ được công bố vào chiều thứ hai.",
    "Đồ ngu, làm việc như thế này thật vô trách nhiệm.",
    "Mình không thấy dịch vụ này tốt như quảng cáo.",
    "Giảng viên giải thích cực kỳ dễ hiểu và rất kiên nhẫn.",
    "Tốt, tốt thật, nhưng giá chưa tốt.",
    "Cảm ơn cô đã hỗ trợ 👍🏽.",
    "Bạn kỹ thuật 👩‍💻 xử lý lỗi khá nhanh.",
    "Ca\u0309m o\u031bn thầy đã dành thời gian hướng dẫn.",
    "  Phòng học\tthoáng.\r\nWifi hơi yếu.  ",
    "Đăng_ký môn học báo lỗi hai lần liên tiếp.",
    "Thông báo: hạn nộp học phí là ngày mai!",
    "Dịch vụ tốt nhưng thời gian chờ quá lâu.",
    "Tôi không hài lòng với cách trả lời thiếu tôn trọng.",
    "Học phí tăng trong khi thiết bị vẫn cũ.",
    "Buổi học bắt đầu lúc tám giờ sáng.",
    "Thầy cô tận tình, bài tập nhiều nhưng có ích.",
    "Trường cung cấp thêm tài liệu và mở phòng tự học, tuy nhiên máy tính thường treo và mạng quá chậm nên sinh viên phải chờ khá lâu.",
]


def _target(prediction, profile):
    label = next(x for x in profile['sentiment'] if x['id']==prediction['sentiment']['label_id'])
    return dict(kind='polarity_margin') if label['key'].casefold() in ('positive','negative') else dict(kind='label_score',label_id=label['id'])


def _calculate(model,tok,alignment,target,profile,seed=42):
    groups=alignment['groups']
    perms,coalitions=generate_permutations(len(groups),8,seed)
    values={};full=None
    for i in range(0,len(coalitions),8):
        batch=coalitions[i:i+8]
        outputs=evaluate_coalition_outputs(model,alignment['full_input_ids'],groups,batch,tokenizer=tok)
        for coalition,output in zip(batch,outputs):
            values[coalition]=target_value(output['sentiment'],target,profile)
            if len(coalition)==len(groups): full=output
    result=compute_shapley_from_coalition_map(groups,perms,values)
    assert result['additivity_residual']<=1e-6
    return result,full,len(coalitions)


@pytest.mark.real_model
def test_real_model_attribution_parity_and_additivity(tmp_path):
    import torch
    root=Path(__file__).resolve().parents[2]
    template=Path(os.environ['FEEDBACK_REAL_BUNDLE_TEMPLATE'])
    runtime=tmp_path/'isolated-real-model'
    bundle=_verify_and_copy_active_bundle(template,runtime/'models')
    registry=ModelRegistry(runtime/'models');profile=profiles()['neu']
    started=time.perf_counter()
    model,tok,pre,identity,manifest=registry.get_loaded_bundle('neu')
    cold_load=time.perf_counter()-started
    warm=[];records=[];stability=[]
    output_dir=Path(os.environ.get('FEEDBACK_FIX_EVIDENCE',root/'test-results'/'codex-fix-20261112'))
    output_dir.mkdir(parents=True,exist_ok=True)
    try:
        # Warm model separately; the 20 timings below are distinct authored inputs.
        registry.predict('neu',[dict(item_id='warmup',revision_id='r',text='Thư viện mở cửa.')])
        for index,text in enumerate(CASES):
            print('REAL_CASE',index,flush=True)
            start=time.perf_counter()
            prediction=registry.predict('neu',[dict(item_id=str(index),revision_id='r',text=text)])[0]
            prediction_seconds=time.perf_counter()-start
            assert prediction['execution_identity']==identity
            alignment=align_and_group(text,tok,preprocessor=pre)
            expected_ids=tok.encode(pre.transform([text])[0],add_special_tokens=True)
            assert alignment['full_input_ids']==expected_ids
            assert not alignment['truncated']
            target=_target(prediction,profile)
            start=time.perf_counter()
            result,full,count=_calculate(model,tok,alignment,target,profile)
            seconds=time.perf_counter()-start;warm.append(seconds)
            check_parity(full,prediction,profile)
            diff={head:max(abs(a-b) for a,b in zip(full[head],prediction[head]['scores'])) for head in ('sentiment','topic')}
            records.append(dict(index=index,text=text,target=target,predicted_label=prediction['sentiment']['label_id'],
                prediction_seconds=prediction_seconds,attribution_seconds=seconds,groups=len(alignment['groups']),
                coalitions=count,parity=diff,aggregate={k:v for k,v in result.items() if k!='groups'},group_values=result['groups']))
            if index in (0,5,14):
                other,_,_=_calculate(model,tok,alignment,target,profile,seed=9173)
                strong=sorted(result['groups'],key=lambda g:abs(g['contribution']),reverse=True)[:3]
                by_id={g['id']:g for g in other['groups']}
                top_other=[g['id'] for g in sorted(other['groups'],key=lambda g:abs(g['contribution']),reverse=True)[:3]]
                stability.append(dict(index=index,seeds=[42,9173],top42=[g['id'] for g in strong],top9173=top_other,
                    top_overlap=len(set(g['id'] for g in strong)&set(top_other)),
                    strong_sign_agreement=sum((g['contribution']>=0)==(by_id[g['id']]['contribution']>=0) for g in strong),
                    values9173=other['groups']))
        truncated=align_and_group('Thư viện rất tốt. '*80,tok,preprocessor=pre)
        assert truncated['truncated']
        assert not registry.status('uit')['available']
    finally:
        timings=sorted(warm)
        evidence=dict(kind='REAL_CHECKPOINT_CPU_FP32',hardware=platform.processor(),python=platform.python_version(),
            torch=torch.__version__,threads=torch.get_num_threads(),batch=8,permutations=8,
            source_checkpoint_sha256=bundle['checkpoint_sha256'],identity=identity,cold_bundle_load_seconds=cold_load,
            warm_count=len(warm),warm_median=statistics.median(warm) if warm else None,
            warm_p95=timings[math.ceil(.95*len(timings))-1] if timings else None,warm_max=max(warm) if warm else None,
            records=records,stability=stability)
        (output_dir/'real-model-benchmark.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    assert len(warm)==20
