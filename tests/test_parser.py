from ai.parser import parse_json_response

def test_layer1_valid_json():
    result = parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}
    assert "_partial" not in result

def test_layer2_code_fence():
    result = parse_json_response('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}

def test_layer3_brace_recovery():
    result = parse_json_response('some text {"key": "value"} more text')
    assert result["key"] == "value"
    assert result.get("_partial")

def test_all_layers_fail():
    result = parse_json_response('completely invalid text')
    assert result.get("_partial")
    assert "_error" in result

def test_empty_response():
    result = parse_json_response('')
    assert result.get("_partial")
