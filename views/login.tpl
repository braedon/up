% rebase('base.tpl', title='up? - Log In')
<main>
  <span class="spacer"></span>
  <div class="content limitWidth">
    <h1>up?</h1>
    <div class="section">
      <a class="mainButton" href="{{oidc_login_uri}}">
        Log In with {{oidc_name}}
      </a>
      <div class="linkRow">
        <a href="{{oidc_about_url}}" target="_blank" rel="noopener noreferrer">
          What's {{oidc_name}}?
        </a>
      </div>
    </div>
  </div>
  <span class="spacer"></span>
</main>
