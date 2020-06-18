% rebase('base.tpl', title='up?', description='Get notified when a link is back up.')
<main>
  % if defined('user_id') and user_id:
  <div class="header">
    <span class="spacer"></span>
    <a class="buttonLike" href="/logout">Log Out</a>
  </div>
  % end
  <span class="spacer"></span>
  <div class="content limitWidth">
    <h1>up?</h1>
    <div class="section">
      <p>
        Got a link that's down?<br>
        Get notified when it's up.
      </p>
    </div>
    % if defined('user_id') and user_id:
    <form class="section" action="/link" method="GET">
      <input type="url" name="url" autocomplete="url" placeholder="Link URL" required>
      <button class="mainButton">Check Link</button>
    </form>
    % else:
    <div class="section">
      <a class="mainButton" href="/login?auto=true">
        Log In with {{oidc_name}}
      </a>
      <div class="linkRow">
        <a href="{{oidc_about_url}}" target="_blank" rel="noopener noreferrer">
          What's {{oidc_name}}?
        </a>
      </div>
    </div>
    % end
  </div>
  <span class="spacer"></span>
</main>
