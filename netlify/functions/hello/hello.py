def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": '{"ok": true, "message": "Python function is alive"}'
    }
