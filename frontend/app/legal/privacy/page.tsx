import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — SuspensionLab",
  description: "Privacy Policy for SuspensionLab.",
};

export default function PrivacyPage() {
  const EFFECTIVE_DATE = "June 12, 2025";
  const COMPANY = "SuspensionLab";
  const EMAIL = "privacy@suspensionlab.io";

  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-3xl mx-auto px-6 py-20 text-gray-300">
        <h1 className="text-4xl font-bold text-white mb-2">Privacy Policy</h1>
        <p className="text-sm text-gray-500 mb-10">Effective Date: {EFFECTIVE_DATE}</p>

        <div className="space-y-10 text-sm leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-white mb-3">1. Introduction</h2>
            <p>{COMPANY} (&ldquo;we&rdquo;, &ldquo;our&rdquo;, &ldquo;us&rdquo;) is committed to protecting your personal information. This Privacy Policy explains how we collect, use, and share data when you use our vehicle dynamics simulation platform.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">2. Information We Collect</h2>
            <ul className="list-disc list-inside space-y-2">
              <li><strong className="text-white">Account data:</strong> Name, email address, and hashed password when you register.</li>
              <li><strong className="text-white">Simulation data:</strong> Vehicle parameters and configurations you submit for simulation.</li>
              <li><strong className="text-white">Usage data:</strong> IP address, browser type, pages visited, and feature usage (via anonymized analytics).</li>
              <li><strong className="text-white">Billing data:</strong> Handled entirely by Lemon Squeezy. We never store your credit card details.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">3. How We Use Your Data</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>To provide and improve the Service.</li>
              <li>To send transactional emails (account creation, billing receipts).</li>
              <li>To respond to support requests.</li>
              <li>To monitor system health and fix errors (via Sentry error tracking).</li>
              <li>We do <strong className="text-white">not</strong> sell your data to third parties.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">4. Data Sharing</h2>
            <p>We share data only with the following trusted service providers, solely to operate the Service:</p>
            <ul className="list-disc list-inside space-y-2 mt-2">
              <li><strong className="text-white">Lemon Squeezy</strong> — Payment processing.</li>
              <li><strong className="text-white">Railway.app</strong> — Cloud infrastructure and hosting.</li>
              <li><strong className="text-white">Sentry.io</strong> — Error monitoring (data is anonymized).</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">5. Data Retention</h2>
            <p>We retain your account data for as long as your account is active. Simulation results are retained for 90 days on the free plan and indefinitely on paid plans. You may request deletion of your data at any time.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">6. Security</h2>
            <p>We use industry-standard security measures including bcrypt password hashing, JWT authentication, HTTPS encryption, and regular security audits. No method of transmission over the Internet is 100% secure.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">7. Your Rights</h2>
            <p>Depending on your jurisdiction, you may have rights to access, correct, or delete your personal data, and to object to or restrict processing. To exercise these rights, contact us at the email below.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">8. Cookies</h2>
            <p>We use essential cookies for authentication (JWT tokens stored in HTTP-only cookies or localStorage). We do not use advertising tracking cookies.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">9. Changes to This Policy</h2>
            <p>We may update this policy periodically. We will notify you of material changes via email at least 14 days in advance.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-white mb-3">10. Contact</h2>
            <p>For privacy-related questions or data requests, contact us at <a href={`mailto:${EMAIL}`} className="text-ansys-yellow hover:underline">{EMAIL}</a>.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
