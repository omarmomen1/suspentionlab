import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — SuspensionLab",
  description: "Terms of Service for SuspensionLab.",
};

export default function TermsPage() {
  const EFFECTIVE_DATE = "June 12, 2025";
  const COMPANY = "SuspensionLab";
  const EMAIL = "legal@suspensionlab.io";

  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-3xl mx-auto px-6 py-20 text-gray-300">
        <h1 className="text-4xl font-bold text-white mb-2">Terms of Service</h1>
        <p className="text-sm text-gray-500 mb-10">Effective Date: {EFFECTIVE_DATE}</p>

        <div className="space-y-10 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-white mb-3">1. Agreement to Terms</h2>
            <p>By accessing or using {COMPANY} (&ldquo;Service&rdquo;), you agree to be bound by these Terms of Service. If you disagree with any part, you may not access the Service.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">2. Description of Service</h2>
            <p>{COMPANY} provides a cloud-based vehicle dynamics simulation platform for engineers and researchers. The Service includes quarter-car, half-car, and full-car suspension simulations, AI-assisted optimization, and analytics tools.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">3. Accounts</h2>
            <p>You must provide accurate information when creating an account. You are responsible for maintaining the security of your account and password. You must notify us immediately of any unauthorized use. We are not liable for losses caused by unauthorized use of your account.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">4. Subscriptions and Billing</h2>
            <p>Paid subscriptions are billed in advance on a monthly or annual basis. All billing is handled securely through Lemon Squeezy. You may cancel at any time; cancellations take effect at the end of the current billing period. No refunds are issued for partial months except where required by law.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">5. Free Tier</h2>
            <p>A free tier is available with limited features. We reserve the right to modify or discontinue the free tier at any time with 30 days&apos; notice.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">6. Acceptable Use</h2>
            <p>You agree not to: (a) use the Service to infringe intellectual property rights; (b) transmit malicious code or interfere with the Service; (c) attempt to gain unauthorized access to any systems; (d) use automated tools to scrape or overload the Service; (e) use the Service for any unlawful purpose.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">7. Intellectual Property</h2>
            <p>The Service and its original content, features, and functionality are owned by {COMPANY} and are protected by international copyright and other intellectual property laws. Your simulation results and data remain yours. You grant us a limited license to process your data to provide the Service.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">8. Disclaimer of Warranties</h2>
            <p>The Service is provided &ldquo;as is&rdquo; without warranty of any kind. We do not warrant that simulation results are accurate for any specific engineering decision. Users are solely responsible for validating results before applying them in real-world engineering contexts.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">9. Limitation of Liability</h2>
            <p>To the maximum extent permitted by law, {COMPANY} shall not be liable for any indirect, incidental, special, consequential, or punitive damages. Our total liability shall not exceed the amount paid by you in the 12 months prior to the claim.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">10. Termination</h2>
            <p>We reserve the right to terminate or suspend your account immediately for violations of these Terms. You may terminate your account at any time by contacting us.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">11. Changes to Terms</h2>
            <p>We may modify these Terms at any time. We will provide at least 14 days&apos; notice of material changes via email or in-app notification. Continued use after changes constitutes acceptance.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">12. Contact</h2>
            <p>For questions about these Terms, contact us at <a href={`mailto:${EMAIL}`} className="text-ansys-yellow hover:underline">{EMAIL}</a>.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
