import os

def patch_file(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath}, does not exist")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace("stripe_customer_id", "billing_customer_id")
    content = content.replace("lemon_customer_id", "billing_customer_id")
    content = content.replace("stripe_subscription_id", "billing_subscription_id")
    content = content.replace("lemon_subscription_id", "billing_subscription_id")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Patched {filepath}")

if __name__ == "__main__":
    patch_file("d:/project/src/suspensionlab/backend/api/routes/billing_routes.py")
    patch_file("d:/project/tests/test_stripe_webhook.py")
    patch_file("d:/project/tests/test_webhook_enterprise_e2e.py")
    patch_file("d:/project/src/suspensionlab/backend/database/models/user.py")
