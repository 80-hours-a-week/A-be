import { test, expect } from '@playwright/test';

// E2E hero flow (US-H1) against the mock-first app — no backend required.
// Phone viewport (NFR-U1). Uses stable data-testid selectors.

test('anonymous → signup → login → search → results', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('hero-landing')).toBeVisible();

  // Anonymous hero shows signup/login CTAs.
  await page.getByTestId('hero-cta-signup').click();
  await page.getByTestId('signup-email').fill('demo@docsuri.dev');
  await page.getByTestId('signup-password').fill('demo-password-123');
  await page.getByTestId('signup-submit').click();

  // Redirected to login.
  await page.getByTestId('login-email').fill('demo@docsuri.dev');
  await page.getByTestId('login-password').fill('demo-password-123');
  await page.getByTestId('login-submit').click();

  // First login → onboarding interest picker (U14, US-OB1). Skipping must not block
  // the session (BR-OB1) and never re-prompts within it.
  await expect(page.getByTestId('interest-picker')).toBeVisible();
  await page.getByTestId('interest-picker-skip').click();
  await expect(page.getByTestId('interest-picker')).toBeHidden();

  // Lands on search; run a query and see ranked cards.
  await page.getByTestId('search-input').fill('transformer attention');
  await page.getByTestId('search-submit').click();
  await expect(page.getByTestId('result-list')).toBeVisible();
  await expect(page.getByTestId('result-card').first()).toBeVisible();
});

test('protected search redirects anonymous users to login', async ({ page }) => {
  await page.goto('/search');
  await expect(page.getByTestId('login-form')).toBeVisible();
});
